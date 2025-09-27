__all__ = [
    "idpathcacher",
    "pantransfercacher",
    "lifeeventcacher",
    "r302cacher",
    "DirectoryCache",
]


from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, MutableMapping, Optional, Union, Set
from time import time

from cachetools import TTLCache as MemoryTTLCache
from diskcache import Cache as DiskCache

from app.core.cache import Cache, LRUCache
from app.core.config import settings
from app.helper.redis import RedisHelper


class IdPathCache:
    """
    文件路径ID缓存
    """

    def __init__(self, maxsize=128):
        self.id_to_dir = LRUCache(
            region="p115strmhelper_id_path_cache_id_to_dir",
            maxsize=maxsize,
        )
        self.dir_to_id = LRUCache(
            region="p115strmhelper_id_path_cache_dir_to_id",
            maxsize=maxsize,
        )

    def add_cache(self, id: int, directory: str):
        """
        添加缓存
        """
        self.id_to_dir.set(key=str(id), value=directory)
        self.dir_to_id.set(key=directory, value=str(id))

    def get_dir_by_id(self, id: int) -> Optional[str]:
        """
        通过 ID 获取路径

        return: str | None
        """
        return self.id_to_dir.get(str(id))

    def get_id_by_dir(self, directory: str) -> Optional[int]:
        """
        通过路径获取 ID

        return: int | None
        """
        _id = self.dir_to_id.get(directory)
        if _id is None:
            return None
        try:
            return int(_id)
        except ValueError:
            return None

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
        self.create_strm_file_dict: MutableMapping[str, List] = MemoryTTLCache(
            maxsize=1_000_000, ttl=600
        )


class R302Cache:
    """
    302 跳转缓存
    """

    def __init__(self, maxsize=8096):
        """
        初始化缓存

        参数:
        maxsize (int): 缓存可以容纳的最大条目数
        """
        self._cache = Cache(maxsize=maxsize)
        self.region = "p115strmhelper_r302_cache"

    def set(self, pick_code, ua_code, url, expires_time):
        """
        向缓存中添加一个URL，并为其设置独立的过期时间。

        参数:
        pick_code (str): 第一层键
        ua_code (str): 第二层键
        url (str): 需要缓存的URL
        expires_time (int): 过期时间
        """
        self._cache.set(
            key=f"{pick_code}○{ua_code}",
            value=url,
            ttl=int(expires_time - time()),
            region=self.region,
        )

    def get(self, pick_code, ua_code) -> Optional[str]:
        """
        从缓存中获取一个URL，如果它存在且未过期

        参数:
        pick_code (str): 第一层键
        ua_code (str): 第二层键

        return: str | None
        str: 如果URL存在且未过期，则返回该URL
        None: 如果URL不存在或已过期
        """
        return self._cache.get(key=f"{pick_code}○{ua_code}", region=self.region)

    def count_by_pick_code(self, pick_code) -> int:
        """
        计算与指定 pick_code 匹配的缓存条目数量。

        参数:
        pick_code (str): 要匹配的第一层键

        return: int
        int: 匹配的缓存条目数量
        """
        count = 0
        for key_str, _ in self._cache.items(region=self.region):
            key = key_str.split("○")
            if key[0] == pick_code:
                count += 1
        return count

    def clear(self):
        """
        清空所有缓存
        """
        self._cache.clear(region=self.region)


class BaseCacheDirectory(ABC):
    """
    缓存目录的抽象基类
    """

    @abstractmethod
    def add_to_group(self, group_name: str, paths: Union[str, List[str]]):
        pass

    @abstractmethod
    def is_in_cache(self, group_name: str, path: str) -> bool:
        pass

    @abstractmethod
    def get_group_paths(self, group_name: str) -> Set[str]:
        pass

    @abstractmethod
    def clear_group(self, group_name: str):
        pass

    @abstractmethod
    def close(self):
        pass


class DiskCacheDirectory(BaseCacheDirectory):
    """
    使用 diskcache 的目录缓存器
    """

    def __init__(self, cache_directory: Path):
        if not cache_directory.exists():
            cache_directory.mkdir(parents=True, exist_ok=True)
        self._cache = DiskCache(cache_directory.as_posix())

    def add_to_group(self, group_name: str, paths: Union[str, List[str]]):
        paths_to_add = {paths} if isinstance(paths, str) else set(paths)
        with self._cache.transact():
            existing_paths = self._cache.get(group_name, set())
            updated_paths = existing_paths.union(paths_to_add)
            self._cache.set(group_name, updated_paths)

    def is_in_cache(self, group_name: str, path: str) -> bool:
        directory_set = self._cache.get(group_name)
        return directory_set is not None and path in directory_set

    def get_group_paths(self, group_name: str) -> Set[str]:
        return self._cache.get(group_name, set())

    def clear_group(self, group_name: str):
        with self._cache.transact():
            if group_name in self._cache:
                del self._cache[group_name]

    def close(self):
        self._cache.close()


class RedisCacheDirectory(BaseCacheDirectory):
    """
    使用 Redis 的目录缓存器
    """

    def __init__(self):
        self.redis_helper = RedisHelper()
        self.redis_helper._connect()
        self.client = self.redis_helper.client
        if self.client is None:
            raise ConnectionError("无法从 RedisHelper 获取有效的 Redis 客户端。")

    def _make_set_key(self, group_name: str) -> str:
        """
        为我们的 Set 创建一个独立的、带前缀的键名，避免与 RedisHelper 中的其他键冲突
        """
        return f"dir_cache_set:{group_name}"

    def add_to_group(self, group_name: str, paths: Union[str, List[str]]):
        key = self._make_set_key(group_name)
        paths_to_add = [paths] if isinstance(paths, str) else paths
        if paths_to_add:
            self.client.sadd(key, *paths_to_add)

    def is_in_cache(self, group_name: str, path: str) -> bool:
        key = self._make_set_key(group_name)
        return self.client.sismember(key, path)

    def get_group_paths(self, group_name: str) -> Set[str]:
        key = self._make_set_key(group_name)
        byte_set = self.client.smembers(key)
        return {b.decode('utf-8') for b in byte_set}

    def clear_group(self, group_name: str):
        key = self._make_set_key(group_name)
        self.client.delete(key)

    def close(self):
        pass


class DirectoryCache:
    """
    一个支持 diskcache 和 Redis 后端的目录缓存模块。
    """

    def __init__(self, cache_directory: Optional[Path] = None):
        """
        初始化目录缓存
        """
        if settings.CACHE_BACKEND_TYPE == "redis":
            self._storage: BaseCacheDirectory = RedisCacheDirectory()
        else:
            self._storage: BaseCacheDirectory = DiskCacheDirectory(cache_directory)

    def add_to_group(self, group_name: str, paths: Union[str, List[str]]):
        self._storage.add_to_group(group_name, paths)

    def is_in_cache(self, group_name: str, path: str) -> bool:
        return self._storage.is_in_cache(group_name, path)

    def get_group_paths(self, group_name: str) -> Set[str]:
        return self._storage.get_group_paths(group_name)

    def clear_group(self, group_name: str):
        self._storage.clear_group(group_name)

    def close(self):
        self._storage.close()


idpathcacher = IdPathCache(maxsize=4096)
pantransfercacher = PanTransferCache()
lifeeventcacher = LifeEventCache()
r302cacher = R302Cache(maxsize=8096)
