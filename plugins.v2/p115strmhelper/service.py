from time import time, sleep
from threading import Event, Thread
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from p115client import P115Client
from p115client.tool.util import share_extract_payload
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from .helper.mediainfo_download import MediaInfoDownloader
from .helper.life import MonitorLife
from .helper.strm import FullSyncStrmHelper, ShareStrmHelper, IncrementSyncStrmHelper
from .helper.monitor import handle_file, FileMonitorHandler
from .helper.share import ShareTransferHelper
from .core.config import configer
from .core.message import post_message
from .core.cache import FullSyncDbCache

from app.log import logger
from app.core.config import settings
from app.schemas import NotificationType


class ServiceHelper:
    """
    服务项
    """

    def __init__(self):
        self.client = None
        self.mediainfodownloader = None
        self.monitorlife = None

        self.sharetransferhelper = None

        self.monitor_stop_event = Event()
        self.monitor_life_thread = None

        self.fullsyncdbcacher = None

        self.scheduler = None

        self.service_observer = []

    def init_service(self):
        """
        初始化服务
        """
        try:
            self.client = P115Client(configer.get_config("cookies"))
            self.mediainfodownloader = MediaInfoDownloader(
                cookie=configer.get_config("cookies")
            )
            self.monitorlife = MonitorLife(
                client=self.client, mediainfodownloader=self.mediainfodownloader
            )
            self.sharetransferhelper = ShareTransferHelper(self.client)
            self.fullsyncdbcacher = FullSyncDbCache(
                cache_dir=configer.get_config("PLUGIN_CACHE_PATH")
            )
            return True
        except Exception as e:
            logger.error(f"服务项初始化失败: {e}")
            return False

    def monitor_life_strm_files(self):
        """
        监控115生活事件
        """
        if not self.monitorlife.check_status():
            return
        logger.info("【监控生活事件】生活事件监控启动中...")
        try:
            from_time = time()
            from_id = 0
            while True:
                if self.monitor_stop_event.is_set():
                    logger.info("【监控生活事件】收到停止信号，退出上传事件监控")
                    break
                from_time, from_id = self.monitorlife.once_pull(
                    from_time=from_time, from_id=from_id
                )
        except Exception as e:
            logger.error(f"【监控生活事件】生活事件监控运行失败: {e}")
            logger.info("【监控生活事件】30s 后尝试重新启动生活事件监控")
            sleep(30)
            self.monitor_life_strm_files()
        logger.info("【监控生活事件】已退出生活事件监控")
        return

    def start_monitor_life(self):
        """
        启动生活事件监控
        """
        if (
            configer.get_config("monitor_life_enabled")
            and configer.get_config("monitor_life_paths")
            and configer.get_config("monitor_life_event_modes")
        ) or (
            configer.get_config("pan_transfer_enabled")
            and configer.get_config("pan_transfer_paths")
        ):
            self.monitor_stop_event.clear()
            if self.monitor_life_thread:
                if not self.monitor_life_thread.is_alive():
                    self.monitor_life_thread = Thread(
                        target=self.monitor_life_strm_files, daemon=True
                    )
                    self.monitor_life_thread.start()
            else:
                self.monitor_life_thread = Thread(
                    target=self.monitor_life_strm_files, daemon=True
                )
                self.monitor_life_thread.start()

    def full_sync_strm_files(self):
        """
        全量同步
        """
        if (
            not configer.get_config("full_sync_strm_paths")
            or not configer.get_config("moviepilot_address")
            or not configer.get_config("user_download_mediaext")
        ):
            return

        strm_helper = FullSyncStrmHelper(
            client=self.client,
            mediainfodownloader=self.mediainfodownloader,
            fullsyncdbcacher=self.fullsyncdbcacher,
        )
        strm_helper.generate_strm_files(
            full_sync_strm_paths=configer.get_config("full_sync_strm_paths"),
        )
        (
            strm_count,
            mediainfo_count,
            strm_fail_count,
            mediainfo_fail_count,
            remove_unless_strm_count,
        ) = strm_helper.get_generate_total()
        if configer.get_config("notify"):
            text = f"""
📄 生成STRM文件 {strm_count} 个
⬇️ 下载媒体文件 {mediainfo_count} 个
❌ 生成STRM失败 {strm_fail_count} 个
🚫 下载媒体失败 {mediainfo_fail_count} 个
"""
            if remove_unless_strm_count != 0:
                text += f"🗑️ 清理无效STRM文件 {remove_unless_strm_count} 个"
            post_message(
                mtype=NotificationType.Plugin,
                title="✅【115网盘】全量生成 STRM 文件完成",
                text=text,
            )

    def start_full_sync(self):
        """
        启动全量同步
        """
        self.scheduler = BackgroundScheduler(timezone=settings.TZ)
        self.scheduler.add_job(
            func=self.full_sync_strm_files,
            trigger="date",
            run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
            name="115网盘助手全量生成STRM",
        )
        if self.scheduler.get_jobs():
            self.scheduler.print_jobs()
            self.scheduler.start()

    def share_strm_files(self):
        """
        分享生成STRM
        """
        if (
            not configer.get_config("user_share_pan_path")
            or not configer.get_config("user_share_local_path")
            or not configer.get_config("moviepilot_address")
        ):
            return

        if configer.get_config("user_share_link"):
            data = share_extract_payload(configer.get_config("user_share_link"))
            share_code = data["share_code"]
            receive_code = data["receive_code"]
            logger.info(
                f"【分享STRM生成】解析分享链接 share_code={share_code} receive_code={receive_code}"
            )
        else:
            if not configer.get_config("user_share_code") or not configer.get_config(
                "user_receive_code"
            ):
                return
            share_code = configer.get_config("user_share_code")
            receive_code = configer.get_config("user_receive_code")

        try:
            strm_helper = ShareStrmHelper(
                client=self.client, mediainfodownloader=self.mediainfodownloader
            )
            strm_helper.get_share_list_creata_strm(
                cid=0,
                share_code=share_code,
                receive_code=receive_code,
            )
            strm_helper.download_mediainfo()
            strm_count, mediainfo_count, strm_fail_count, mediainfo_fail_count = (
                strm_helper.get_generate_total()
            )
            if configer.get_config("notify"):
                post_message(
                    mtype=NotificationType.Plugin,
                    title="✅【115网盘】分享生成 STRM 文件完成",
                    text=f"\n📄 生成STRM文件 {strm_count} 个\n"
                    + f"⬇️ 下载媒体文件 {mediainfo_count} 个\n"
                    + f"❌ 生成STRM失败 {strm_fail_count} 个\n"
                    + f"🚫 下载媒体失败 {mediainfo_fail_count} 个",
                )
        except Exception as e:
            logger.error(f"【分享STRM生成】运行失败: {e}")
            return

    def start_share_sync(self):
        """
        启动分享同步
        """
        self.scheduler = BackgroundScheduler(timezone=settings.TZ)
        self.scheduler.add_job(
            func=self.share_strm_files,
            trigger="date",
            run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
            name="115网盘助手分享生成STRM",
        )
        if self.scheduler.get_jobs():
            self.scheduler.print_jobs()
            self.scheduler.start()

    def increment_sync_strm_files(self, send_msg: bool = False):
        """
        增量同步
        """
        if (
            not configer.get_config("increment_sync_strm_paths")
            or not configer.get_config("moviepilot_address")
            or not configer.get_config("user_download_mediaext")
        ):
            return

        strm_helper = IncrementSyncStrmHelper(
            client=self.client, mediainfodownloader=self.mediainfodownloader
        )
        strm_helper.generate_strm_files(
            sync_strm_paths=configer.get_config("increment_sync_strm_paths"),
        )
        (
            strm_count,
            mediainfo_count,
            strm_fail_count,
            mediainfo_fail_count,
        ) = strm_helper.get_generate_total()
        if configer.get_config("notify") and (
            send_msg
            or (
                strm_count != 0
                or mediainfo_count != 0
                or strm_fail_count != 0
                or mediainfo_fail_count != 0
            )
        ):
            text = f"""
📄 生成STRM文件 {strm_count} 个
⬇️ 下载媒体文件 {mediainfo_count} 个
❌ 生成STRM失败 {strm_fail_count} 个
🚫 下载媒体失败 {mediainfo_fail_count} 个
"""
            post_message(
                mtype=NotificationType.Plugin,
                title="✅【115网盘】增量生成 STRM 文件完成",
                text=text,
            )

    def event_handler(self, event, mon_path: str, text: str, event_path: str):
        """
        处理文件变化
        :param event: 事件
        :param mon_path: 监控目录
        :param text: 事件描述
        :param event_path: 事件文件路径
        """
        if not event.is_directory:
            # 文件发生变化
            logger.debug(f"【目录上传】文件 {text}: {event_path}")
            handle_file(event_path=event_path, mon_path=mon_path)

    def start_directory_upload(self):
        """
        启动目录上传监控
        """
        if configer.get_config("directory_upload_enabled"):
            for item in configer.get_config("directory_upload_path"):
                if not item:
                    continue
                mon_path = item.get("src", "")
                if not mon_path:
                    continue
                try:
                    if configer.get_config("directory_upload_mode") == "compatibility":
                        # 兼容模式，目录同步性能降低且NAS不能休眠，但可以兼容挂载的远程共享目录如SMB
                        observer = PollingObserver(timeout=10)
                    else:
                        # 内部处理系统操作类型选择最优解
                        observer = Observer(timeout=10)
                    self.service_observer.append(observer)
                    observer.schedule(
                        FileMonitorHandler(mon_path, self),
                        path=mon_path,
                        recursive=True,
                    )
                    observer.daemon = True
                    observer.start()
                    logger.info(f"【目录上传】{mon_path} 实时监控服务启动")
                except Exception as e:
                    err_msg = str(e)
                    if "inotify" in err_msg and "reached" in err_msg:
                        logger.warn(
                            f"【目录上传】监控服务启动出现异常：{err_msg}，请在宿主机上（不是docker容器内）执行以下命令并重启："
                            + """
                                echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
                                echo fs.inotify.max_user_instances=524288 | sudo tee -a /etc/sysctl.conf
                                sudo sysctl -p
                                """
                        )
                    else:
                        logger.error(
                            f"【目录上传】{mon_path} 启动实时监控失败：{err_msg}"
                        )

    def main_cleaner(self):
        """
        主清理模块
        """
        if configer.get_config("clear_receive_path_enabled"):
            self.clear_receive_path()

        if configer.get_config("clear_recyclebin_enabled"):
            self.clear_recyclebin()

    def clear_recyclebin(self):
        """
        清空回收站
        """
        try:
            logger.info("【回收站清理】开始清理回收站")
            self.client.recyclebin_clean(password=configer.get_config("password"))
            logger.info("【回收站清理】回收站已清空")
        except Exception as e:
            logger.error(f"【回收站清理】清理回收站运行失败: {e}")
            return

    def clear_receive_path(self):
        """
        清空最近接收
        """
        try:
            logger.info("【最近接收清理】开始清理最近接收")
            parent_id = int(self.client.fs_dir_getid("/最近接收")["id"])
            if parent_id == 0:
                logger.info("【最近接收清理】最近接收目录为空，无需清理")
                return
            logger.info(f"【最近接收清理】最近接收目录 ID 获取成功: {parent_id}")
            self.client.fs_delete(parent_id)
            logger.info("【最近接收清理】最近接收已清空")
        except Exception as e:
            logger.error(f"【最近接收清理】清理最近接收运行失败: {e}")
            return

    def stop(self):
        """
        停止所有服务
        """
        try:
            if self.service_observer:
                for observer in self.service_observer:
                    try:
                        observer.stop()
                        observer.join()
                        logger.debug(f"【目录上传】{observer} 关闭")
                    except Exception as e:
                        logger.error(f"【目录上传】关闭失败: {e}")
                logger.info("【目录上传】目录监控已关闭")
            self.service_observer = []
            if self.scheduler:
                self.scheduler.remove_all_jobs()
                if self.scheduler.running:
                    self.scheduler.shutdown()
                self.scheduler = None
            self.monitor_stop_event.set()
            if self.fullsyncdbcacher:
                self.fullsyncdbcacher.shutdown()
        except Exception as e:
            logger.error(f"发生错误: {e}")


servicer = ServiceHelper()
