import shutil
import time
from collections import defaultdict
from threading import Timer
from typing import List, Set
from pathlib import Path
from itertools import batched, chain

from ..core.config import configer
from ..core.message import post_message
from ..core.scrape import media_scrape_metadata
from ..core.cache import idpathcacher, pantransfercacher, lifeeventcacher
from ..core.i18n import i18n
from ..utils.path import PathUtils, PathRemoveUtils
from ..utils.sentry import sentry_manager
from ..utils.strm import StrmUrlGetter, StrmGenerater
from ..utils.automaton import AutomatonUtils
from ..utils.mediainfo_download import MediainfoDownloadMiddleware
from ..db_manager.oper import FileDbHelper
from ..helper.mediainfo_download import MediaInfoDownloader
from ..helper.mediasyncdel import MediaSyncDelHelper
from ..helper.mediaserver import MediaServerRefresh

from p115client import P115Client
from p115client.tool.attr import get_path
from p115client.tool.iterdir import iter_files_with_path
from p115client.tool.life import (
    iter_life_behavior_once,
    life_show,
    BEHAVIOR_TYPE_TO_NAME,
)

from app.schemas import NotificationType, FileItem
from app.log import logger
from app.core.config import settings
from app.chain.storage import StorageChain
from app.chain.transfer import TransferChain


@sentry_manager.capture_all_class_exceptions
class MonitorLife:
    """
    监控115生活事件

    {
        1: "upload_image_file",  上传图片 生成 STRM;写入数据库
        2: "upload_file",        上传文件/目录 生成 STRM;写入数据库
        3: "star_image",         标星图片 无操作
        4: "star_file",          标星文件/目录 无操作
        5: "move_image_file",    移动图片 生成 STRM;写入数据库
        6: "move_file",          移动文件/目录 生成 STRM;写入数据库
        7: "browse_image",       浏览图片 无操作
        8: "browse_video",       浏览视频 无操作
        9: "browse_audio",       浏览音频 无操作
        10: "browse_document",   浏览文档 无操作
        14: "receive_files",     接收文件 生成 STRM;写入数据库
        17: "new_folder",        创建新目录 写入数据库
        18: "copy_folder",       复制文件夹 生成 STRM;写入数据库
        19: "folder_label",      标签文件夹 无操作
        20: "folder_rename",     重命名文件夹 无操作
        22: "delete_file",       删除文件/文件夹 删除 STRM;移除数据库
    }

    注意: 目前没有重命名文件，复制文件的操作事件
    """

    def __init__(self, client: P115Client, mediainfodownloader: MediaInfoDownloader):
        self._client = client
        self.mediainfodownloader = mediainfodownloader

        self._monitor_life_notification_timer = None
        self._monitor_life_notification_queue = defaultdict(
            lambda: {"strm_count": 0, "mediainfo_count": 0}
        )

        self.rmt_mediaext: List = []
        self.rmt_mediaext_set: Set = set()
        self.download_mediaext_set: Set = set()

        self.mdaw = AutomatonUtils.build_automaton(
            configer.mediainfo_download_whitelist
        )
        self.mdab = AutomatonUtils.build_automaton(
            configer.mediainfo_download_blacklist
        )

        self.mediaserver_helper = MediaServerRefresh(
            func_name="【监控生活事件】",
            enabled=configer.monitor_life_media_server_refresh_enabled,
            mp_mediaserver=configer.monitor_life_mp_mediaserver_paths,
            mediaservers=configer.monitor_life_mediaservers,
        )

    def _schedule_notification(self):
        """
        安排通知发送，如果一分钟内没有新事件则发送
        """
        if self._monitor_life_notification_timer:
            self._monitor_life_notification_timer.cancel()

        self._monitor_life_notification_timer = Timer(60.0, self._send_notification)
        self._monitor_life_notification_timer.start()

    def _send_notification(self):
        """
        发送合并后的通知
        """
        if "life" not in self._monitor_life_notification_queue:
            return

        counts = self._monitor_life_notification_queue["life"]
        if counts["strm_count"] == 0 and counts["mediainfo_count"] == 0:
            return

        text_parts = []
        if counts["strm_count"] > 0:
            text_parts.append(f"📄 生成STRM文件 {counts['strm_count']} 个")
        if counts["mediainfo_count"] > 0:
            text_parts.append(f"⬇️ 下载媒体文件 {counts['mediainfo_count']} 个")

        if text_parts and configer.get_config("notify"):
            post_message(
                mtype=NotificationType.Plugin,
                title=i18n.translate("life_sync_done_title"),
                text="\n" + "\n".join(text_parts),
            )

        # 重置计数器
        self._monitor_life_notification_queue["life"] = {
            "strm_count": 0,
            "mediainfo_count": 0,
        }

    def _get_path_by_cid(self, cid: int):
        """
        通过 cid 获取路径
        先从缓存获取，再从数据库获取，最后通过API获取
        """
        if int(cid) == 0:
            return Path("/")
        _databasehelper = FileDbHelper()
        dir_path = idpathcacher.get_dir_by_id(cid)
        if not dir_path:
            data = _databasehelper.get_by_id(id=cid)
            if data:
                dir_path = data.get("path", None)
                if dir_path:
                    logger.debug(f"获取 {cid} 路径（数据库）: {dir_path}")
                    idpathcacher.add_cache(id=cid, directory=str(dir_path))
                    return Path(dir_path)
            dir_path = get_path(client=self._client, attr=cid, root_id=None)
            idpathcacher.add_cache(id=cid, directory=str(dir_path))
            if not dir_path:
                logger.error(f"获取 {cid} 路径失败")
                return None
            logger.debug(f"获取 {cid} 路径（API）: {dir_path}")
            return Path(dir_path)
        logger.debug(f"获取 {cid} 路径（缓存）: {dir_path}")
        return Path(dir_path)

    def media_transfer(self, event, file_path: Path, rmt_mediaext):
        """
        运行媒体文件整理
        :param event: 事件
        :param file_path: 文件路径
        :param rmt_mediaext: 媒体文件后缀名
        """
        _databasehelper = FileDbHelper()
        transferchain = TransferChain()
        file_category = event["file_category"]
        file_id = event["file_id"]
        if file_category == 0:
            cache_top_path = False
            cache_file_id_list = []
            logger.info(f"【网盘整理】开始处理 {file_path} 文件夹中...")
            _databasehelper.remove_by_id_batch(int(event["file_id"]), False)
            # 文件夹情况，遍历文件夹，获取整理文件
            # 缓存顶层文件夹ID
            if str(event["file_id"]) not in pantransfercacher.delete_pan_transfer_list:
                pantransfercacher.delete_pan_transfer_list.append(str(event["file_id"]))
            for item in iter_files_with_path(
                self._client, cid=int(file_id), cooldown=2
            ):
                file_path = Path(item["path"])
                # 缓存文件夹ID
                if (
                    str(item["parent_id"])
                    not in pantransfercacher.delete_pan_transfer_list
                ):
                    pantransfercacher.delete_pan_transfer_list.append(
                        str(item["parent_id"])
                    )
                if file_path.suffix.lower() in rmt_mediaext:
                    # 缓存文件ID
                    if (
                        str(item["id"])
                        not in pantransfercacher.creata_pan_transfer_list
                    ):
                        pantransfercacher.creata_pan_transfer_list.append(
                            str(item["id"])
                        )
                    # 判断此顶层目录MP是否能处理
                    if str(item["parent_id"]) != event["file_id"]:
                        cache_top_path = True
                    if str(item["id"]) not in cache_file_id_list:
                        cache_file_id_list.append(str(item["id"]))
                    transferchain.do_transfer(
                        fileitem=FileItem(
                            storage="u115",
                            fileid=str(item["id"]),
                            parent_fileid=str(item["parent_id"]),
                            path=file_path.as_posix(),
                            type="file",
                            name=file_path.name,
                            basename=file_path.stem,
                            extension=file_path.suffix[1:].lower(),
                            size=item["size"],
                            pickcode=item["pickcode"],
                            modify_time=item["ctime"],
                        )
                    )
                    logger.info(f"【网盘整理】{file_path} 加入整理列队")
                if (
                    file_path.suffix.lower() in settings.RMT_AUDIOEXT
                    or file_path.suffix.lower() in settings.RMT_SUBEXT
                ):
                    # 如果是MP可处理的音轨或字幕文件，则缓存文件ID
                    if (
                        str(item["id"])
                        not in pantransfercacher.creata_pan_transfer_list
                    ):
                        pantransfercacher.creata_pan_transfer_list.append(
                            str(item["id"])
                        )

            # 顶层目录MP无法处理时添加到缓存字典中
            if cache_top_path and cache_file_id_list:
                if (
                    str(event["file_id"])
                    in pantransfercacher.top_delete_pan_transfer_list
                ):
                    # 如果存在相同ID的根目录则合并
                    cache_file_id_list = list(
                        dict.fromkeys(
                            chain(
                                cache_file_id_list,
                                pantransfercacher.top_delete_pan_transfer_list[
                                    str(event["file_id"])
                                ],
                            )
                        )
                    )
                    del pantransfercacher.top_delete_pan_transfer_list[
                        str(event["file_id"])
                    ]
                pantransfercacher.top_delete_pan_transfer_list[
                    str(event["file_id"])
                ] = cache_file_id_list
        else:
            # 文件情况，直接整理
            if file_path.suffix.lower() in rmt_mediaext:
                _databasehelper.remove_by_id("file", event["file_id"])
                # 缓存文件ID
                if (
                    str(event["file_id"])
                    not in pantransfercacher.creata_pan_transfer_list
                ):
                    pantransfercacher.creata_pan_transfer_list.append(
                        str(event["file_id"])
                    )
                transferchain.do_transfer(
                    fileitem=FileItem(
                        storage="u115",
                        fileid=str(file_id),
                        parent_fileid=str(event["parent_id"]),
                        path=file_path.as_posix(),
                        type="file",
                        name=file_path.name,
                        basename=file_path.stem,
                        extension=file_path.suffix[1:].lower(),
                        size=event["file_size"],
                        pickcode=event["pick_code"],
                        modify_time=event["update_time"],
                    )
                )
                logger.info(f"【网盘整理】{file_path} 加入整理列队")

    def creata_strm(self, event, file_path):
        """
        创建 STRM 文件
        """
        _databasehelper = FileDbHelper()

        _get_url = StrmUrlGetter()

        pickcode = event["pick_code"]
        file_category = event["file_category"]
        file_id = event["file_id"]
        status, target_dir, pan_media_dir = PathUtils.get_media_path(
            configer.get_config("monitor_life_paths"), file_path
        )
        if not status:
            return
        logger.debug("【监控生活事件】匹配到网盘文件夹路径: %s", str(pan_media_dir))

        if file_category == 0:
            # 文件夹情况，遍历文件夹
            mediainfo_count = 0
            strm_count = 0
            _databasehelper.upsert_batch(
                _databasehelper.process_life_dir_item(event=event, file_path=file_path)
            )
            for batch in batched(
                iter_files_with_path(self._client, cid=int(file_id), cooldown=2),
                7_000,
            ):
                processed = []
                for item in batch:
                    _process_item = _databasehelper.process_item(item)
                    if _process_item not in processed:
                        processed.extend(_process_item)
                    if item["is_dir"]:
                        continue
                    if "creata" in configer.get_config("monitor_life_event_modes"):  # pylint: disable=E1135
                        file_path = item["path"]
                        file_path = Path(target_dir) / Path(file_path).relative_to(
                            pan_media_dir
                        )
                        file_target_dir = file_path.parent
                        original_file_name = file_path.name
                        file_name = file_path.stem + ".strm"
                        new_file_path = file_target_dir / file_name

                        if configer.get_config(
                            "monitor_life_auto_download_mediainfo_enabled"
                        ):
                            if file_path.suffix.lower() in self.download_mediaext_set:
                                if not (
                                    result
                                    := MediainfoDownloadMiddleware.should_download(
                                        filename=original_file_name,
                                        blacklist_automaton=self.mdab,
                                        whitelist_automaton=self.mdaw,
                                    )
                                )[1]:
                                    logger.warning(
                                        "【监控生活事件】%s，跳过网盘路径: %s",
                                        result[0],
                                        item["path"],
                                    )
                                    continue

                                pickcode = item["pickcode"]
                                if not pickcode:
                                    logger.error(
                                        f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                                    )
                                    continue
                                download_url = (
                                    self.mediainfodownloader.get_download_url(
                                        pickcode=pickcode
                                    )
                                )

                                if not download_url:
                                    logger.error(
                                        f"【监控生活事件】{original_file_name} 下载链接获取失败，无法下载该文件"
                                    )
                                    continue

                                self.mediainfodownloader.save_mediainfo_file(
                                    file_path=Path(file_path),
                                    file_name=original_file_name,
                                    download_url=download_url,
                                )
                                mediainfo_count += 1
                                continue

                        if file_path.suffix.lower() not in self.rmt_mediaext_set:
                            logger.warn(
                                "【监控生活事件】跳过网盘路径: %s",
                                item["path"],
                            )
                            continue

                        if not (
                            result := StrmGenerater.should_generate_strm(
                                original_file_name, "life", item.get("size", None)
                            )
                        )[1]:
                            logger.warn(
                                f"【监控生活事件】{result[0]}，跳过网盘路径: {item['path']}"
                            )
                            continue

                        pickcode = item["pickcode"]
                        if not pickcode:
                            pickcode = item["pick_code"]

                        new_file_path.parent.mkdir(parents=True, exist_ok=True)

                        if not pickcode:
                            logger.error(
                                f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法生成 STRM 文件"
                            )
                            continue
                        if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                            logger.error(
                                f"【监控生活事件】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                            )
                            continue

                        strm_url = _get_url.get_strm_url(pickcode, original_file_name)

                        with open(new_file_path, "w", encoding="utf-8") as file:
                            file.write(strm_url)
                        logger.info(
                            "【监控生活事件】生成 STRM 文件成功: %s",
                            str(new_file_path),
                        )
                        strm_count += 1
                        scrape_metadata = True
                        if configer.get_config("monitor_life_scrape_metadata_enabled"):
                            if configer.get_config(
                                "monitor_life_scrape_metadata_exclude_paths"
                            ):
                                if PathUtils.get_scrape_metadata_exclude_path(
                                    configer.get_config(
                                        "monitor_life_scrape_metadata_exclude_paths"
                                    ),
                                    str(new_file_path),
                                ):
                                    logger.debug(
                                        f"【监控生活事件】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                                    )
                                    scrape_metadata = False
                            if scrape_metadata:
                                media_scrape_metadata(
                                    path=new_file_path,
                                )
                        # 刷新媒体服务器
                        self.mediaserver_helper.refresh_mediaserver(
                            file_path=str(new_file_path),
                            file_name=str(original_file_name),
                        )
                _databasehelper.upsert_batch(processed)
            if configer.get_config("notify"):
                if strm_count > 0 or mediainfo_count > 0:
                    self._monitor_life_notification_queue["life"]["strm_count"] += (
                        strm_count
                    )
                    self._monitor_life_notification_queue["life"][
                        "mediainfo_count"
                    ] += mediainfo_count
                    self._schedule_notification()
        else:
            _databasehelper.upsert_batch(
                _databasehelper.process_life_file_item(event=event, file_path=file_path)
            )
            if "creata" in configer.get_config("monitor_life_event_modes"):  # pylint: disable=E1135
                # 文件情况，直接生成
                file_path = Path(target_dir) / Path(file_path).relative_to(
                    pan_media_dir
                )
                file_target_dir = file_path.parent
                original_file_name = file_path.name
                file_name = file_path.stem + ".strm"
                new_file_path = file_target_dir / file_name

                if configer.get_config("monitor_life_auto_download_mediainfo_enabled"):
                    if file_path.suffix.lower() in self.download_mediaext_set:
                        if not (
                            result := MediainfoDownloadMiddleware.should_download(
                                filename=original_file_name,
                                blacklist_automaton=self.mdab,
                                whitelist_automaton=self.mdaw,
                            )
                        )[1]:
                            logger.warning(
                                "【监控生活事件】%s，跳过网盘路径: %s",
                                result[0],
                                str(file_path).replace(str(target_dir), "", 1),
                            )
                            return

                        if not pickcode:
                            logger.error(
                                f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                            )
                            return
                        download_url = self.mediainfodownloader.get_download_url(
                            pickcode=pickcode
                        )

                        if not download_url:
                            logger.error(
                                f"【监控生活事件】{original_file_name} 下载链接获取失败，无法下载该文件"
                            )
                            return

                        self.mediainfodownloader.save_mediainfo_file(
                            file_path=Path(file_path),
                            file_name=original_file_name,
                            download_url=download_url,
                        )
                        # 下载的元数据写入缓存，与整理事件对比
                        lifeeventcacher.create_strm_file_dict[str(event["file_id"])] = [
                            event["file_name"],
                            target_dir,
                            pan_media_dir,
                        ]
                        if configer.get_config("notify"):
                            self._monitor_life_notification_queue["life"][
                                "mediainfo_count"
                            ] += 1
                            self._schedule_notification()
                        return

                if file_path.suffix.lower() not in self.rmt_mediaext_set:
                    logger.warn(
                        "【监控生活事件】跳过网盘路径: %s",
                        str(file_path).replace(str(target_dir), "", 1),
                    )
                    return

                if not (
                    result := StrmGenerater.should_generate_strm(
                        original_file_name, "life", event.get("file_size", None)
                    )
                )[1]:
                    logger.warn(
                        f"【监控生活事件】{result[0]}，跳过网盘路径: {str(file_path).replace(str(target_dir), '', 1)}"
                    )
                    return

                new_file_path.parent.mkdir(parents=True, exist_ok=True)

                if not pickcode:
                    logger.error(
                        f"【监控生活事件】{original_file_name} 不存在 pickcode 值，无法生成 STRM 文件"
                    )
                    return
                if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                    logger.error(
                        f"【监控生活事件】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                    )
                    return

                strm_url = _get_url.get_strm_url(pickcode, original_file_name)

                with open(new_file_path, "w", encoding="utf-8") as file:
                    file.write(strm_url)
                logger.info(
                    "【监控生活事件】生成 STRM 文件成功: %s", str(new_file_path)
                )
                # 生成的STRM写入缓存，与整理事件对比
                lifeeventcacher.create_strm_file_dict[str(event["file_id"])] = [
                    event["file_name"],
                    target_dir,
                    pan_media_dir,
                ]
                if configer.get_config("notify"):
                    self._monitor_life_notification_queue["life"]["strm_count"] += 1
                    self._schedule_notification()
                scrape_metadata = True
                if configer.get_config("monitor_life_scrape_metadata_enabled"):
                    if configer.get_config(
                        "monitor_life_scrape_metadata_exclude_paths"
                    ):
                        if PathUtils.get_scrape_metadata_exclude_path(
                            configer.get_config(
                                "monitor_life_scrape_metadata_exclude_paths"
                            ),
                            str(new_file_path),
                        ):
                            logger.debug(
                                f"【监控生活事件】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                            )
                            scrape_metadata = False
                    if scrape_metadata:
                        media_scrape_metadata(
                            path=new_file_path,
                        )
                # 刷新媒体服务器
                self.mediaserver_helper.refresh_mediaserver(
                    file_path=new_file_path.as_posix(),
                    file_name=str(original_file_name),
                )

    def remove_strm(self, event):
        """
        删除 STRM 文件
        """

        # def __get_file_path(
        #     file_name: str, file_size: str, file_id: str, file_category: int
        # ):
        #     """
        #     通过 还原文件/文件夹 再删除 获取文件路径
        #     """
        #     for item in self._client.recyclebin_list()["data"]:
        #         if (
        #             file_category == 0
        #             and str(item["file_name"]) == file_name
        #             and str(item["type"]) == "2"
        #         ) or (
        #             file_category != 0
        #             and str(item["file_name"]) == file_name
        #             and str(item["file_size"]) == file_size
        #         ):
        #             resp = self._client.recyclebin_revert(item["id"])
        #             if resp["state"]:
        #                 time.sleep(1)
        #                 path = get_path_to_cid(self._client, cid=int(item["cid"]))
        #                 time.sleep(1)
        #                 self._client.fs_delete(file_id)
        #                 return str(Path(path) / item["file_name"])
        #             else:
        #                 return None
        #     return None

        _databasehelper = FileDbHelper()

        file_path = None
        file_category = event["file_category"]
        file_item = _databasehelper.get_by_id(int(event["file_id"]))
        if file_item:
            file_path = file_item.get("path", "")
        if not file_path:
            logger.debug(
                f"【监控生活事件】{event['file_name']} 无法通过数据库获取路径，防止误删不处理"
            )
            return
        logger.debug(f"【监控生活事件】通过数据库获取路径：{file_path}")

        pan_file_path = file_path
        # 优先匹配待整理目录，如果删除的目录为待整理目录则不进行操作
        if configer.get_config("pan_transfer_enabled") and configer.get_config(
            "pan_transfer_paths"
        ):
            if PathUtils.get_run_transfer_path(
                paths=configer.get_config("pan_transfer_paths"),
                transfer_path=file_path,
            ):
                logger.debug(
                    f"【监控生活事件】{file_path} 为待整理目录下的路径，不做处理"
                )
                return

        # 匹配是否是媒体文件夹目录
        status, target_dir, pan_media_dir = PathUtils.get_media_path(
            configer.get_config("monitor_life_paths"), file_path
        )
        if not status:
            return
        logger.debug("【监控生活事件】匹配到网盘文件夹路径: %s", str(pan_media_dir))

        # 清理数据库此路径记录
        _databasehelper.remove_by_path(
            path_type="folder" if file_category == 0 else "file",
            path=str(pan_file_path),
        )

        storagechain = StorageChain()
        fileitem = storagechain.get_file_item(storage="u115", path=Path(file_path))
        if fileitem:
            logger.warn(
                f"【监控生活事件】网盘 {file_path} 目录存在，跳过本地删除: {fileitem}"
            )
            # 这里如果路径存在则更新数据库信息
            _databasehelper.upsert_batch(
                _databasehelper.process_fileitem(fileitem=fileitem)
            )
            return

        file_path = Path(target_dir) / Path(file_path).relative_to(pan_media_dir)
        if file_path.suffix.lower() in self.rmt_mediaext_set:
            file_target_dir = file_path.parent
            file_name = file_path.stem + ".strm"
            file_path = file_target_dir / file_name
        logger.info(
            f"【监控生活事件】删除本地{'文件夹' if file_category == 0 else '文件'}: {file_path}"
        )
        try:
            if not Path(file_path).exists():
                logger.warn(f"【监控生活事件】本地 {file_path} 不存在，跳过删除")
                return
            if file_category == 0:
                # 删除目录
                shutil.rmtree(Path(file_path))
            else:
                # 删除文件
                Path(file_path).unlink(missing_ok=True)
                # 判断父目录是否需要删除
                PathRemoveUtils.remove_parent_dir(
                    file_path=Path(file_path),
                    mode=["strm"],
                    func_type="【监控生活事件】",
                )
            # 清理数据库所有路径
            _databasehelper.remove_by_path_batch(
                path=str(pan_file_path), only_file=False
            )
            logger.info(f"【监控生活事件】{file_path} 已删除")
            # 同步删除历史记录
            if configer.monitor_life_remove_mp_history:
                mediasyncdel = MediaSyncDelHelper()
                del_torrent_hashs, stop_torrent_hashs, error_cnt, transfer_history = (
                    mediasyncdel.remove_by_path(
                        path=pan_file_path,
                        del_source=configer.monitor_life_remove_mp_source,
                    )
                )
                if configer.notify and transfer_history:
                    torrent_cnt_msg = ""
                    if del_torrent_hashs:
                        torrent_cnt_msg += (
                            f"删除种子 {len(set(del_torrent_hashs))} 个\n"
                        )
                    if stop_torrent_hashs:
                        stop_cnt = 0
                        # 排除已删除
                        for stop_hash in set(stop_torrent_hashs):
                            if stop_hash not in set(del_torrent_hashs):
                                stop_cnt += 1
                        if stop_cnt > 0:
                            torrent_cnt_msg += f"暂停种子 {stop_cnt} 个\n"
                    if error_cnt:
                        torrent_cnt_msg += f"删种失败 {error_cnt} 个\n"
                    post_message(
                        mtype=NotificationType.Plugin,
                        title=i18n.translate("life_sync_media_del_title"),
                        text=f"\n删除{'文件夹' if file_category == 0 else '文件'} {pan_file_path}\n"
                        f"删除记录{len(transfer_history) if transfer_history else '0'}个\n"
                        f"{torrent_cnt_msg}"
                        f"时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n",
                    )
        except Exception as e:
            logger.error(f"【监控生活事件】{file_path} 删除失败: {e}")

    def new_creata_path(self, event):
        """
        处理新出现的路径
        """
        # 1.获取绝对文件路径
        file_name = event["file_name"]
        dir_path = self._get_path_by_cid(int(event["parent_id"]))
        file_path = Path(dir_path) / file_name
        # 匹配逻辑 整理路径目录 > 生成STRM文件路径目录
        # 2.匹配是否为整理路径目录
        if configer.get_config("pan_transfer_enabled") and configer.get_config(
            "pan_transfer_paths"
        ):
            if PathUtils.get_run_transfer_path(
                paths=configer.get_config("pan_transfer_paths"),
                transfer_path=file_path,
            ):
                self.media_transfer(
                    event=event,
                    file_path=Path(file_path),
                    rmt_mediaext=self.rmt_mediaext,
                )
                return
        # 3.匹配是否为生成STRM文件路径目录
        if configer.get_config("monitor_life_enabled") and configer.get_config(
            "monitor_life_paths"
        ):
            if str(event["file_id"]) in pantransfercacher.creata_pan_transfer_list:
                # 检查是否命中缓存
                pantransfercacher.creata_pan_transfer_list.remove(str(event["file_id"]))
                if "transfer" in configer.get_config("monitor_life_event_modes"):  # pylint: disable=E1135
                    self.creata_strm(event=event, file_path=file_path)
            else:
                self.creata_strm(event=event, file_path=file_path)

    def once_pull(self, from_time, from_id):
        """
        单次拉取
        """
        while True:
            if not TransferChain().get_queue_tasks():
                break
            logger.debug(
                "【监控生活事件】MoviePilot 整理运行中，等待整理完成后继续监控生活事件..."
            )
            time.sleep(20)

        events_batch: List = []
        return_from_time: int = from_time
        return_from_id: int = from_id

        for attempt in range(3, -1, -1):
            try:
                # 每次尝试先清空旧的值
                events_batch: List = []
                return_from_time: int = from_time
                return_from_id: int = from_id

                events_iterator = iter_life_behavior_once(
                    client=self._client,
                    from_time=from_time,
                    from_id=from_id,
                    app="web",
                    cooldown=2,
                )

                try:
                    first_event = next(events_iterator)
                except StopIteration:
                    # 迭代器为空，没有数据，属于正常情况
                    break

                if "update_time" in first_event and "id" in first_event:
                    return_from_id = int(first_event["id"])
                    return_from_time = int(first_event["update_time"])
                else:
                    break

                events_batch = [first_event]
                events_batch.extend(list(events_iterator))
                break
            except Exception as e:
                if attempt <= 0:
                    logger.error("【监控生活事件】拉取数据失败：%s", e)
                    raise
                logger.warn(
                    "【监控生活事件】拉取数据失败，剩余重试次数 {attempt} 次：%s", e
                )
                time.sleep(2)

        if not events_batch:
            time.sleep(20)
            return from_time, from_id

        for event in reversed(events_batch):
            self.rmt_mediaext = [
                f".{ext.strip()}"
                for ext in configer.get_config("user_rmt_mediaext")
                .replace("，", ",")
                .split(",")
            ]
            self.rmt_mediaext_set = set(self.rmt_mediaext)
            self.download_mediaext_set = {
                f".{ext.strip()}"
                for ext in configer.get_config("user_download_mediaext")
                .replace("，", ",")
                .split(",")
            }

            logger.debug(
                f"【监控生活事件】{BEHAVIOR_TYPE_TO_NAME.get(event['type'], '未知类型')}: {event}"
            )

            if (
                int(event["type"]) != 1
                and int(event["type"]) != 2
                and int(event["type"]) != 5
                and int(event["type"]) != 6
                and int(event["type"]) != 14
                and int(event["type"]) != 17
                and int(event["type"]) != 18
                and int(event["type"]) != 22
            ):
                continue

            if (
                int(event["type"]) == 1
                or int(event["type"]) == 2
                or int(event["type"]) == 5
                or int(event["type"]) == 6
                or int(event["type"]) == 14
                or int(event["type"]) == 18
            ):
                # 新路径事件处理
                self.new_creata_path(event=event)

            if int(event["type"]) == 22:
                # 删除文件/文件夹事件处理
                if str(event["file_id"]) in pantransfercacher.delete_pan_transfer_list:
                    # 检查是否命中删除文件夹缓存，命中则无需处理
                    pantransfercacher.delete_pan_transfer_list.remove(
                        str(event["file_id"])
                    )
                else:
                    if (
                        configer.get_config("monitor_life_enabled")
                        and configer.get_config("monitor_life_paths")
                        and "remove" in configer.get_config("monitor_life_event_modes")  # pylint: disable=E1135
                    ):
                        self.remove_strm(event=event)

            if int(event["type"]) == 17:
                # 对于创建文件夹事件直接写入数据库
                _databasehelper = FileDbHelper()
                file_name = event["file_name"]
                dir_path = self._get_path_by_cid(int(event["parent_id"]))
                file_path = Path(dir_path) / file_name
                _databasehelper.upsert_batch(
                    _databasehelper.process_life_dir_item(
                        event=event, file_path=file_path
                    )
                )
        return return_from_time, return_from_id

    def check_status(self):
        """
        检查生活事件开启状态
        """
        resp = life_show(self._client)
        if not resp["state"]:
            logger.error(f"【监控生活事件】生活事件开启失败: {resp}")
            return False
        return True
