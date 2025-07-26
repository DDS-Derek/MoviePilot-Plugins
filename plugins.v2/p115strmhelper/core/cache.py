import time
import uuid
from typing import List, Dict, MutableMapping
from threading import Thread, Event

from cachetools import LRUCache, TTLCache
from diskcache import Cache as DCache

from app.log import logger

from ..db_manager.oper import FileDbHelper


class IdPathCache:
    """
    文件路径ID缓存
    """

    def __init__(self, maxsize=128):
        self.id_to_dir = LRUCache(maxsize=maxsize)
        self.dir_to_id = LRUCache(maxsize=maxsize)

    def add_cache(self, id: int, directory: str):
        """
        添加缓存
        """
        self.id_to_dir[id] = directory
        self.dir_to_id[directory] = id

    def get_dir_by_id(self, id: int):
        """
        通过 ID 获取路径
        """
        return self.id_to_dir.get(id)

    def get_id_by_dir(self, directory: str):
        """
        通过路径获取 ID
        """
        return self.dir_to_id.get(directory)

    def clear(self):
        """
        清空所有缓存
        """
        self.id_to_dir.clear()
        self.dir_to_id.clear()


class PanTransferCache:
    """
    网盘整理缓存
    """

    def __init__(self):
        self.delete_pan_transfer_list = []
        self.creata_pan_transfer_list = []
        self.top_delete_pan_transfer_list: Dict[str, List] = {}


class LifeEventCache:
    """
    生活事件监控缓存
    """

    def __init__(self):
        self.create_strm_file_dict: MutableMapping[str, List] = TTLCache(
            maxsize=1_000_000, ttl=600
        )


class FullSyncDbCache:
    """
    全量同步数据库写入缓存
    """

    def __init__(self, cache_dir=".diskcache", batch_size=1000, flush_interval=2):
        """
        初始化缓冲写入器

        参数:
            cache_dir: DiskCache缓存目录
            batch_size: 每次批量写入的大小
            flush_interval: 后台刷新间隔(秒)
        """
        self.db = FileDbHelper()
        self.cache = DCache(cache_dir)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._stop_event = Event()
        self._worker_thread = Thread(target=self._background_worker, daemon=True)
        self._worker_thread.start()

    def upsert_batch(self, batch: List[Dict]):
        """
        写入数据到缓存
        """
        with self.cache.transact():
            for item in batch:
                key = f"{item['data']['id']}_{item['data']['name']}_{uuid.uuid4().hex}"
                self.cache.set(key, item)

    def _background_worker(self):
        """
        后台工作线程，定期将缓存数据写入数据库
        """
        while not self._stop_event.is_set():
            time.sleep(self.flush_interval)
            if self.cache:
                logger.debug(f"【全量STRM生成】本地缓存数量：{len(self.cache)}")
            self._flush_cache_to_db()

    def _flush_cache_to_db(self):
        """
        将缓存数据批量写入数据库
        """
        with self.cache.transact():
            batch = []
            keys_to_delete = []

            for key in self.cache:
                value = self.cache[key]
                batch.append(value)
                keys_to_delete.append(key)

                if len(batch) >= self.batch_size:
                    break

            if batch:
                try:
                    self.db.upsert_batch(batch)
                    for key in keys_to_delete:
                        del self.cache[key]
                except Exception as e:
                    logger.error(f"【全量STRM生成】缓存模块数据库写入失败: {e}")

    def shutdown(self):
        """
        关闭时刷新所有剩余数据
        """
        self._stop_event.set()
        self._worker_thread.join()
        self.cache.close()


idpathcacher = IdPathCache()
pantransfercacher = PanTransferCache()
lifeeventcacher = LifeEventCache()
