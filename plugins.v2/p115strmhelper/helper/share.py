import threading
import time
from queue import Queue, Empty

from p115client import P115Client
from p115client.tool.iterdir import share_iterdir
from p115client.tool.util import share_extract_payload

from app.log import logger
from app.core.metainfo import MetaInfo
from app.chain.media import MediaChain

from ..core.config import configer
from ..core.message import post_message
from ..core.cache import idpathcacher
from ..core.i18n import i18n
from ..utils.sentry import capture_all_class_exceptions


@capture_all_class_exceptions
class ShareTransferHelper:
    """
    分享链接转存
    """

    def __init__(self, client: P115Client):
        self.client = client
        self._add_share_queue = Queue()
        self._add_share_worker_thread = None
        self._add_share_worker_lock = threading.Lock()

    def _ensure_add_share_worker_running(self):
        """
        确保工作线程正在运行
        """
        with self._add_share_worker_lock:
            if (
                self._add_share_worker_thread is None
                or not self._add_share_worker_thread.is_alive()
            ):
                self._add_share_worker_thread = threading.Thread(
                    target=self._process_add_share_queue, daemon=True
                )
                self._add_share_worker_thread.start()

    def _process_add_share_queue(self):
        """
        处理队列中的任务
        """
        while True:
            try:
                # 获取任务，设置超时避免永久阻塞
                task = self._add_share_queue.get(timeout=60)  # 60秒无任务则退出
                url, channel, userid = task

                # 执行任务
                self.__add_share(url, channel, userid)

                # 任务间隔
                time.sleep(3)

                # 标记任务完成
                self._add_share_queue.task_done()

            except Empty:
                logger.debug("【分享转存】释放分享转存队列进程")
                break
            except Exception as e:
                logger.error(f"【分享转存】任务处理异常: {e}")
                time.sleep(5)

    def add_share_recognize_mediainfo(self, share_code: str, receive_code: str):
        """
        分享转存识别媒体信息
        """
        file_num = 0
        file_mediainfo = None
        for item in share_iterdir(
            self.client,
            receive_code=receive_code,
            share_code=share_code,
            cid=0,
        ):
            if file_num == 1:
                file_num = 2
                break
            item_name = item["name"]
            file_num += 1
        if file_num == 1:
            mediachain = MediaChain()
            file_meta = MetaInfo(title=item_name)
            file_mediainfo = mediachain.recognize_by_meta(file_meta)
        return file_mediainfo

    @staticmethod
    def share_url_extract(url: str):
        """
        解析分享链接
        """
        return share_extract_payload(url)

    def __add_share(self, url, channel, userid):
        """
        分享转存
        """
        if not configer.get_config("pan_transfer_enabled") or not configer.get_config(
            "pan_transfer_paths"
        ):
            post_message(
                channel=channel,
                title=i18n.translate("add_share_config_error"),
                userid=userid,
            )
            return
        try:
            data = self.share_url_extract(url)
            share_code = data["share_code"]
            receive_code = data["receive_code"]
            logger.info(
                f"【分享转存】解析分享链接 share_code={share_code} receive_code={receive_code}"
            )
            if not share_code or not receive_code:
                logger.error(f"【分享转存】解析分享链接失败：{url}")
                post_message(
                    channel=channel,
                    title=f"{i18n.translate('share_url_extract_error', url=url)}",
                    userid=userid,
                )
                return
            parent_path = configer.get_config("pan_transfer_paths").split("\n")[0]
            parent_id = idpathcacher.get_id_by_dir(directory=str(parent_path))
            if not parent_id:
                parent_id = self.client.fs_dir_getid(parent_path)["id"]
                logger.info(f"【分享转存】获取到转存目录 ID：{parent_id}")
                idpathcacher.add_cache(id=int(parent_id), directory=str(parent_path))
            payload = {
                "share_code": share_code,
                "receive_code": receive_code,
                "file_id": 0,
                "cid": int(parent_id),
                "is_check": 0,
            }

            # 尝试识别媒体信息
            file_mediainfo = self.add_share_recognize_mediainfo(
                share_code=share_code, receive_code=receive_code
            )

            resp = self.client.share_receive(payload)
            if resp["state"]:
                logger.info(f"【分享转存】转存 {share_code} 到 {parent_path} 成功！")
                if not file_mediainfo:
                    post_message(
                        channel=channel,
                        title=i18n.translate("share_add_success"),
                        text=f"""
分享链接：https://115cdn.com/s/{share_code}?password={receive_code}
转存目录：{parent_path}
""",
                        userid=userid,
                    )
                else:
                    post_message(
                        channel=channel,
                        title=i18n.translate(
                            "share_add_success_2",
                            title=file_mediainfo.title,
                            year=file_mediainfo.year,
                        ),
                        text=f"""
链接：https://115cdn.com/s/{share_code}?password={receive_code}
简介：{file_mediainfo.overview}
""",
                        image=file_mediainfo.poster_path,
                        userid=userid,
                    )
            else:
                logger.info(f"【分享转存】转存 {share_code} 失败：{resp['error']}")
                post_message(
                    channel=channel,
                    title=i18n.translate("share_add_fail"),
                    text=f"""
分享链接：https://115cdn.com/s/{share_code}?password={receive_code}
转存目录：{parent_path}
失败原因：{resp["error"]}
""",
                    userid=userid,
                )
            return
        except Exception as e:
            logger.error(f"【分享转存】运行失败: {e}")
            post_message(
                channel=channel,
                title=i18n.translate("share_add_fail_2", e=e),
                userid=userid,
            )
            return

    def add_share(self, url, channel, userid):
        """
        将分享任务加入队列
        """
        self._add_share_queue.put((url, channel, userid))
        logger.info(
            f"【分享转存】{url} 任务已加入分享转存队列，当前队列大小：{self._add_share_queue.qsize()}"
        )
        self._ensure_add_share_worker_running()
