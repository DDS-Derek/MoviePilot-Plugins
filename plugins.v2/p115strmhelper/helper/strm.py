import time
import threading
import shutil
from typing import List, Dict, Optional
from pathlib import Path
from itertools import batched
import concurrent.futures

from sqlalchemy.orm.exc import MultipleResultsFound
from p115client import P115Client
from p115client.tool.export_dir import export_dir_parse_iter
from p115client.tool.fs_files import iter_fs_files
from p115client.tool.iterdir import iter_files_with_path, share_iterdir

from ..core.cache import idpathcacher, FullSyncDbCache
from ..core.config import configer
from ..utils.tree import DirectoryTree
from ..core.scrape import media_scrape_metadata
from ..db_manager.oper import FileDbHelper
from ..utils.path import PathUtils
from ..helper.mediainfo_download import MediaInfoDownloader

from app.log import logger
from app.core.config import settings
from app.core.meta import MetaBase
from app.core.context import MediaInfo
from app.chain.storage import StorageChain
from app.schemas import RefreshMediaItem, ServiceInfo, TransferInfo
from app.helper.mediaserver import MediaServerHelper
from app.utils.system import SystemUtils


class IncrementSyncStrmHelper:
    """
    增量同步 STRM 文件
    """

    def __init__(self, client: P115Client, mediainfodownloader: MediaInfoDownloader):
        self.client = client
        self.mediainfodownloader = mediainfodownloader
        self.rmt_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_rmt_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.download_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_download_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.auto_download_mediainfo = configer.get_config(
            "increment_sync_auto_download_mediainfo_enabled"
        )
        self.mp_mediaserver_paths = configer.get_config(
            "increment_sync_mp_mediaserver_paths"
        )
        self.scrape_metadata_enabled = configer.get_config(
            "increment_sync_scrape_metadata_enabled"
        )
        self.scrape_metadata_exclude_paths = configer.get_config(
            "increment_sync_scrape_metadata_exclude_paths"
        )
        self.media_server_refresh_enabled = configer.get_config(
            "increment_sync_media_server_refresh_enabled"
        )
        self.mediaservers = configer.get_config("increment_sync_mediaservers")
        self.strm_count = 0
        self.mediainfo_count = 0
        self.strm_fail_count = 0
        self.mediainfo_fail_count = 0
        self.api_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = None
        self.server_address = configer.get_config("moviepilot_address").rstrip("/")
        self.pan_transfer_enabled = configer.get_config("pan_transfer_enabled")
        self.pan_transfer_paths = configer.get_config("pan_transfer_paths")
        self.strm_url_format = configer.get_config("strm_url_format")
        self.databasehelper = FileDbHelper()
        self.download_mediainfo_list = []

        # 临时文件配置
        self.local_tree = (
            configer.get_config("PLUGIN_TEMP_PATH") / "increment_local_tree.txt"
        )
        self.pan_tree = (
            configer.get_config("PLUGIN_TEMP_PATH") / "increment_pan_tree.txt"
        )
        self.pan_to_local_tree = (
            configer.get_config("PLUGIN_TEMP_PATH") / "increment_pan_to_local_tree.txt"
        )

    def __itertree(self, pan_path: str, local_path: str):
        """
        迭代目录树
        """
        relative_path = None
        cid = int(self.client.fs_dir_getid(pan_path)["id"])
        self.api_count += 2
        cnt = 0
        for item in export_dir_parse_iter(
            client=self.client, export_file_ids=cid, delete=True
        ):
            if cnt < 1:
                cnt += 1
                continue
            elif cnt == 1:
                relative_path = item
                cnt += 1
                continue
            item_path = Path(pan_path) / Path(item).relative_to(relative_path)
            if item_path.name != item_path.stem:
                if item_path.suffix in self.rmt_mediaext:
                    yield (
                        str(
                            Path(local_path)
                            / Path(item_path.relative_to(pan_path)).with_suffix(".strm")
                        ),
                        str(item_path),
                    )
                elif (
                    item_path.suffix in self.download_mediaext
                    and self.auto_download_mediainfo
                ):
                    yield (
                        str(Path(local_path) / Path(item_path.relative_to(pan_path))),
                        str(item_path),
                    )

    def __iterdir(self, cid: int, path: str):
        """
        迭代网盘目录
        """
        logger.debug(f"【增量STRM生成】迭代网盘目录: {cid} {path}")
        for batch in iter_fs_files(self.client, cid):
            self.api_count += 1
            for item in batch.get("data", []):
                item["path"] = path + "/" + item.get("n")
                yield item

    def __get_cid_by_path(self, path: str):
        """
        通过路径获取 cid
        先从缓存获取，再从数据库获取
        """
        cid = idpathcacher.get_id_by_dir(path)
        if not cid:
            # 这里如果有多条重复数据就不进行删除文件夹操作了，说明数据库重复过多，直接放弃
            data = self.databasehelper.get_by_path(path=path)
            if data:
                cid = data.get("id", None)
                if cid:
                    logger.debug(f"【增量STRM生成】获取 {path} cid（数据库）: {cid}")
                    idpathcacher.add_cache(id=int(cid), directory=path)
                    return int(cid)
            return None
        logger.debug(f"【增量STRM生成】获取 {path} cid（缓存）: {cid}")
        return int(cid)

    def __get_pickcode(self, path: str):
        """
        通过路径获取 pickcode
        """
        while True:
            # 这里如果有多条重复数据直接删除文件重复信息，然后迭代重新获取
            try:
                file_item = self.databasehelper.get_by_path(path=path)
            except MultipleResultsFound:
                self.databasehelper.remove_by_path_batch(path=path, only_file=True)
                file_item = None
            if file_item:
                return file_item.get("pickcode")
            file_path = Path(path)
            temp_path = None
            for part in file_path.parents:
                cid = self.__get_cid_by_path(str(part))
                if cid:
                    temp_path = part
                    break
            if not temp_path:
                raise ValueError(f"无法找到路径 {path} 对应的 cid")
            for batch in batched(self.__iterdir(cid=cid, path=str(temp_path)), 7_000):
                processed: List = []
                for item in batch:
                    processed.extend(self.databasehelper.process_fs_files_item(item))
                self.databasehelper.upsert_batch(processed)
            time.sleep(2)

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        媒体服务器服务信息
        """
        if not self.mediaservers:
            logger.warning("【增量STRM生成】尚未配置媒体服务器，请检查配置")
            return None

        mediaserver_helper = MediaServerHelper()

        services = mediaserver_helper.get_services(name_filters=self.mediaservers)
        if not services:
            logger.warning("【增量STRM生成】获取媒体服务器实例失败，请检查配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(
                    f"【增量STRM生成】媒体服务器 {service_name} 未连接，请检查配置"
                )
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("【增量STRM生成】没有已连接的媒体服务器，请检查配置")
            return None

        return active_services

    def __refresh_mediaserver(self, file_path: str, file_name: str):
        """
        刷新媒体服务器
        """
        if self.media_server_refresh_enabled:
            if not self.service_infos:
                return
            logger.info(f"【增量STRM生成】{file_name} 开始刷新媒体服务器")
            if self.mp_mediaserver_paths:
                status, mediaserver_path, moviepilot_path = PathUtils.get_media_path(
                    self.mp_mediaserver_paths, file_path
                )
                if status:
                    logger.debug(
                        f"【增量STRM生成】{file_name} 刷新媒体服务器目录替换中..."
                    )
                    file_path = file_path.replace(
                        moviepilot_path, mediaserver_path
                    ).replace("\\", "/")
                    logger.debug(
                        f"【增量STRM生成】刷新媒体服务器目录替换: {moviepilot_path} --> {mediaserver_path}"
                    )
                    logger.info(f"【增量STRM生成】刷新媒体服务器目录: {file_path}")
            items = [
                RefreshMediaItem(
                    title=None,
                    year=None,
                    type=None,
                    category=None,
                    target_path=Path(file_path),
                )
            ]
            for name, service in self.service_infos.items():
                if hasattr(service.instance, "refresh_library_by_items"):
                    service.instance.refresh_library_by_items(items)
                elif hasattr(service.instance, "refresh_root_library"):
                    service.instance.refresh_root_library()
                else:
                    logger.warning(f"【增量STRM生成】{file_name} {name} 不支持刷新")

    def __generate_local_tree(self, target_dir: str):
        """
        生成本地目录树
        """
        tree = DirectoryTree()

        if Path(self.local_tree).exists():
            Path(self.local_tree).unlink(missing_ok=True)

        def background_task(target_dir, local_tree):
            """
            后台运行任务
            """
            logger.info(f"【增量STRM生成】开始扫描本地媒体库文件: {target_dir}")
            tree.scan_directory_to_tree(
                root_path=target_dir,
                output_file=local_tree,
                append=False,
                extensions=[".strm"]
                if not self.auto_download_mediainfo
                else [".strm"] + self.download_mediaext,
            )
            logger.info(f"【增量STRM生成】扫描本地媒体库文件完成: {target_dir}")

        local_tree_task_thread = threading.Thread(
            target=background_task,
            args=(
                target_dir,
                self.local_tree,
            ),
        )
        local_tree_task_thread.start()

        return local_tree_task_thread

    @staticmethod
    def __wait_generate_local_tree(thread):
        """
        等待生成本地目录树运行完成
        """
        while thread.is_alive():
            logger.info("【增量STRM生成】扫描本地媒体库运行中...")
            time.sleep(10)

    def __generate_pan_tree(self, pan_media_dir: str, target_dir: str):
        """
        生成网盘目录树
        """
        tree = DirectoryTree()

        if Path(self.pan_tree).exists():
            Path(self.pan_tree).unlink(missing_ok=True)
        if Path(self.pan_to_local_tree).exists():
            Path(self.pan_to_local_tree).unlink(missing_ok=True)

        logger.info(f"【增量STRM生成】开始生成网盘目录树: {pan_media_dir}")

        for path1, path2 in self.__itertree(
            pan_path=pan_media_dir, local_path=target_dir
        ):
            tree.generate_tree_from_list([path1], self.pan_to_local_tree, append=True)
            tree.generate_tree_from_list([path2], self.pan_tree, append=True)

        logger.info(f"【增量STRM生成】网盘目录树生成完成: {pan_media_dir}")

    def __handle_addition_path(self, pan_path: str, local_path: str):
        """
        处理新增路径
        """
        try:
            pan_path = Path(pan_path)
            new_file_path = Path(local_path)

            if self.pan_transfer_enabled and self.pan_transfer_paths:
                if PathUtils.get_run_transfer_path(
                    paths=self.pan_transfer_paths,
                    transfer_path=str(pan_path),
                ):
                    logger.debug(
                        f"【增量STRM生成】{pan_path} 为待整理目录下的路径，不做处理"
                    )
                    return

            if self.auto_download_mediainfo:
                if pan_path.suffix in self.download_mediaext:
                    pickcode = self.__get_pickcode(str(pan_path))
                    if not pickcode:
                        logger.error(
                            f"【增量STRM生成】{pan_path.name} 不存在 pickcode 值，无法下载该文件"
                        )
                        return
                    self.download_mediainfo_list.append(
                        {
                            "type": "local",
                            "pickcode": pickcode,
                            "path": local_path,
                        }
                    )
                    return

            if pan_path.suffix not in self.rmt_mediaext:
                logger.warn(f"【增量STRM生成】跳过网盘路径: {pan_path}")
                return

            pickcode = self.__get_pickcode(str(pan_path))

            new_file_path.parent.mkdir(parents=True, exist_ok=True)

            if not pickcode:
                self.strm_fail_count += 1
                self.strm_fail_dict[str(new_file_path)] = "不存在 pickcode 值"
                logger.error(
                    f"【增量STRM生成】{pan_path.name} 不存在 pickcode 值，无法生成 STRM 文件"
                )
                return
            if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                self.strm_fail_count += 1
                self.strm_fail_dict[str(new_file_path)] = (
                    f"错误的 pickcode 值 {pickcode}"
                )
                logger.error(
                    f"【增量STRM生成】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                )
                return
            strm_url = f"{self.server_address}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={pickcode}"
            if self.strm_url_format == "pickname":
                strm_url += f"&file_name={pan_path.name}"

            with open(new_file_path, "w", encoding="utf-8") as file:
                file.write(strm_url)
            self.strm_count += 1
            logger.info(
                "【增量STRM生成】生成 STRM 文件成功: %s",
                str(new_file_path),
            )
        except Exception as e:
            logger.error(
                "【增量STRM生成】生成 STRM 文件失败: %s  %s",
                str(new_file_path),
                e,
            )
            self.strm_fail_count += 1
            self.strm_fail_dict[str(new_file_path)] = str(e)
            return
        if self.scrape_metadata_enabled:
            scrape_metadata = True
            if self.scrape_metadata_exclude_paths:
                if PathUtils.get_scrape_metadata_exclude_path(
                    self.scrape_metadata_exclude_paths,
                    str(new_file_path),
                ):
                    logger.debug(
                        f"【增量STRM生成】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                    )
                    scrape_metadata = False
            if scrape_metadata:
                media_scrape_metadata(
                    path=str(new_file_path),
                )
        # 刷新媒体服务器
        self.__refresh_mediaserver(str(new_file_path), str(new_file_path.name))

    def generate_strm_files(self, sync_strm_paths):
        """
        生成 STRM 文件
        """
        tree = DirectoryTree()
        media_paths = sync_strm_paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 1)
            pan_media_dir = parts[1]
            target_dir = parts[0]

            if pan_media_dir == "/" or target_dir == "/":
                logger.error(
                    f"【增量STRM生成】网盘目录或本地生成目录不能为根目录: {path}"
                )

            pan_media_dir = pan_media_dir.rstrip("/")
            target_dir = target_dir.rstrip("/")

            try:
                # 生成本地目录树文件
                local_tree_task_thread = self.__generate_local_tree(
                    target_dir=target_dir
                )

                # 生成网盘目录树文件
                self.__generate_pan_tree(
                    pan_media_dir=pan_media_dir, target_dir=target_dir
                )

                # 等待生成本地目录树运行完成
                self.__wait_generate_local_tree(local_tree_task_thread)

                # 生成或者下载文件
                for line in tree.compare_trees_lines(
                    self.pan_to_local_tree, self.local_tree
                ):
                    self.__handle_addition_path(
                        pan_path=str(tree.get_path_by_line_number(self.pan_tree, line)),
                        local_path=str(
                            tree.get_path_by_line_number(self.pan_to_local_tree, line)
                        ),
                    )
            except Exception as e:
                logger.error(f"【增量STRM生成】增量同步 STRM 文件失败: {e}")
                return

        # 下载媒体信息文件
        self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict = (
            self.mediainfodownloader.auto_downloader(
                downloads_list=self.download_mediainfo_list
            )
        )

        # 日志输出
        if self.strm_fail_dict:
            for path, error in self.strm_fail_dict.items():
                logger.warn(f"【增量STRM生成】{path} 生成错误原因: {error}")
        if self.mediainfo_fail_dict:
            for path in self.mediainfo_fail_dict:
                logger.warn(f"【增量STRM生成】{path} 下载错误")
        logger.info(
            f"【增量STRM生成】增量生成 STRM 文件完成，总共生成 {self.strm_count} 个 STRM 文件，下载 {self.mediainfo_count} 个媒体数据文件"
        )
        if self.strm_fail_count != 0 or self.mediainfo_fail_count != 0:
            logger.warn(
                f"【增量STRM生成】{self.strm_fail_count} 个 STRM 文件生成失败，{self.mediainfo_fail_count} 个媒体数据文件下载失败"
            )
        logger.info(f"【增量STRM生成】API 请求次数 {self.api_count} 次")

    def get_generate_total(self):
        """
        输出总共生成文件个数
        """
        return (
            self.strm_count,
            self.mediainfo_count,
            self.strm_fail_count,
            self.mediainfo_fail_count,
        )


class FullSyncStrmHelper:
    """
    全量生成 STRM 文件
    """

    def __init__(
        self,
        client: P115Client,
        mediainfodownloader: MediaInfoDownloader,
        fullsyncdbcacher: FullSyncDbCache,
    ):
        self.rmt_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_rmt_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.download_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_download_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.auto_download_mediainfo = configer.get_config(
            "full_sync_auto_download_mediainfo_enabled"
        )
        self.client = client
        self.mediainfodownloader = mediainfodownloader
        self.fullsyncdbcacher = fullsyncdbcacher
        self.total_count = 0
        self.strm_count = 0
        self.mediainfo_count = 0
        self.strm_fail_count = 0
        self.mediainfo_fail_count = 0
        self.remove_unless_strm_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = None
        self.server_address = configer.get_config("moviepilot_address").rstrip("/")
        self.pan_transfer_enabled = configer.get_config("pan_transfer_enabled")
        self.pan_transfer_paths = configer.get_config("pan_transfer_paths")
        self.strm_url_format = configer.get_config("strm_url_format")
        self.overwrite_mode = configer.get_config("full_sync_overwrite_mode")
        self.remove_unless_strm = configer.get_config("full_sync_remove_unless_strm")
        self.databasehelper = FileDbHelper()
        self.download_mediainfo_list = []

        self.local_tree = configer.get_config("PLUGIN_TEMP_PATH") / "local_tree.txt"
        self.pan_tree = configer.get_config("PLUGIN_TEMP_PATH") / "pan_tree.txt"

    @staticmethod
    def __remove_parent_dir(file_path: Path):
        """
        删除父目录
        """
        # 删除空目录
        # 判断当前媒体父路径下是否有文件，如有则无需遍历父级
        if not any(file_path.parent.iterdir()):
            # 判断父目录是否为空, 为空则删除
            i = 0
            for parent_path in file_path.parents:
                i += 1
                if i > 3:
                    break
                if str(parent_path.parent) != str(file_path.root):
                    # 父目录非根目录，才删除父目录
                    if not any(parent_path.iterdir()):
                        # 当前路径下没有媒体文件则删除
                        shutil.rmtree(parent_path)
                        logger.warn(f"【全量STRM生成】本地空目录 {parent_path} 已删除")

    def generate_strm_files(self, full_sync_strm_paths):
        """
        生成 STRM 文件
        """
        tree = DirectoryTree()
        media_paths = full_sync_strm_paths.split("\n")
        start_time = time.perf_counter()
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 1)
            pan_media_dir = parts[1]
            target_dir = parts[0]

            if self.remove_unless_strm:
                if Path(self.local_tree).exists():
                    Path(self.local_tree).unlink(missing_ok=True)
                if Path(self.pan_tree).exists():
                    Path(self.pan_tree).unlink(missing_ok=True)

                def background_task(target_dir, local_tree):
                    """
                    后台运行任务
                    """
                    logger.info(f"【全量STRM生成】开始扫描本地媒体库文件: {target_dir}")
                    tree.scan_directory_to_tree(
                        root_path=target_dir,
                        output_file=local_tree,
                        append=False,
                        extensions=[".strm"],
                    )
                    logger.info(f"【全量STRM生成】扫描本地媒体库文件完成: {target_dir}")

                local_tree_task_thread = threading.Thread(
                    target=background_task,
                    args=(
                        target_dir,
                        self.local_tree,
                    ),
                )
                local_tree_task_thread.start()

            try:
                parent_id = int(self.client.fs_dir_getid(pan_media_dir)["id"])
                logger.info(f"【全量STRM生成】网盘媒体目录 ID 获取成功: {parent_id}")
            except Exception as e:
                logger.error(f"【全量STRM生成】网盘媒体目录 ID 获取失败: {e}")
                return False

            try:
                for batch in batched(
                    iter_files_with_path(
                        self.client, cid=parent_id, with_ancestors=True, cooldown=1
                    ),
                    2_000,
                ):
                    processed: List = []
                    path_list: List = []

                    def _process_single_item(item, target_dir, pan_media_dir):
                        path_entry = None
                        self.total_count += 1
                        _process_item = self.databasehelper.process_item(item)
                        try:
                            if item["is_dir"]:
                                return _process_item, path_entry
                            file_path = item["path"]
                            file_path = Path(target_dir) / Path(file_path).relative_to(
                                pan_media_dir
                            )
                            file_target_dir = file_path.parent
                            original_file_name = file_path.name
                            file_name = file_path.stem + ".strm"
                            new_file_path = file_target_dir / file_name
                        except Exception as e:
                            logger.error(
                                "【全量STRM生成】生成 STRM 文件失败: %s  %s",
                                str(item),
                                e,
                            )
                            self.strm_fail_count += 1
                            self.strm_fail_dict[str(item)] = str(e)
                            return _process_item, path_entry

                        try:
                            if self.pan_transfer_enabled and self.pan_transfer_paths:
                                if PathUtils.get_run_transfer_path(
                                    paths=self.pan_transfer_paths,
                                    transfer_path=item["path"],
                                ):
                                    logger.debug(
                                        f"【全量STRM生成】{item['path']} 为待整理目录下的路径，不做处理"
                                    )
                                    return _process_item, path_entry

                            if self.auto_download_mediainfo:
                                if file_path.suffix in self.download_mediaext:
                                    if file_path.exists():
                                        if self.overwrite_mode == "never":
                                            logger.warn(
                                                f"【全量STRM生成】{file_path} 已存在，覆盖模式 {self.overwrite_mode}，跳过此路径"
                                            )
                                            return _process_item, path_entry
                                        else:
                                            logger.warn(
                                                f"【全量STRM生成】{file_path} 已存在，覆盖模式 {self.overwrite_mode}"
                                            )
                                    pickcode = item["pickcode"]
                                    if not pickcode:
                                        logger.error(
                                            f"【全量STRM生成】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                                        )
                                        return _process_item, path_entry
                                    self.download_mediainfo_list.append(
                                        {
                                            "type": "local",
                                            "pickcode": pickcode,
                                            "path": file_path,
                                        }
                                    )
                                    return _process_item, path_entry

                            if file_path.suffix not in self.rmt_mediaext:
                                logger.warn(
                                    "【全量STRM生成】跳过网盘路径: %s",
                                    str(file_path).replace(str(target_dir), "", 1),
                                )
                                return _process_item, path_entry

                            if self.remove_unless_strm:
                                path_entry = str(new_file_path)

                            if new_file_path.exists():
                                if self.overwrite_mode == "never":
                                    logger.warn(
                                        f"【全量STRM生成】{new_file_path} 已存在，覆盖模式 {self.overwrite_mode}，跳过此路径"
                                    )
                                    return _process_item, path_entry
                                else:
                                    logger.warn(
                                        f"【全量STRM生成】{new_file_path} 已存在，覆盖模式 {self.overwrite_mode}"
                                    )

                            pickcode = item["pickcode"]
                            if not pickcode:
                                pickcode = item["pick_code"]

                            new_file_path.parent.mkdir(parents=True, exist_ok=True)

                            if not pickcode:
                                self.strm_fail_count += 1
                                self.strm_fail_dict[str(new_file_path)] = (
                                    "不存在 pickcode 值"
                                )
                                logger.error(
                                    f"【全量STRM生成】{original_file_name} 不存在 pickcode 值，无法生成 STRM 文件"
                                )
                                return _process_item, path_entry
                            if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                                self.strm_fail_count += 1
                                self.strm_fail_dict[str(new_file_path)] = (
                                    f"错误的 pickcode 值 {pickcode}"
                                )
                                logger.error(
                                    f"【全量STRM生成】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                                )
                                return _process_item, path_entry
                            strm_url = f"{self.server_address}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={pickcode}"
                            if self.strm_url_format == "pickname":
                                strm_url += f"&file_name={original_file_name}"

                            with open(new_file_path, "w", encoding="utf-8") as file:
                                file.write(strm_url)
                            self.strm_count += 1
                            logger.info(
                                "【全量STRM生成】生成 STRM 文件成功: %s",
                                str(new_file_path),
                            )
                            return _process_item, path_entry
                        except Exception as e:
                            logger.error(
                                "【全量STRM生成】生成 STRM 文件失败: %s  %s",
                                str(new_file_path),
                                e,
                            )
                            self.strm_fail_count += 1
                            self.strm_fail_dict[str(new_file_path)] = str(e)
                            return _process_item, path_entry

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=128
                    ) as executor:
                        future_to_item = {
                            executor.submit(
                                _process_single_item, item, target_dir, pan_media_dir
                            ): item
                            for item in batch
                        }

                        for future in concurrent.futures.as_completed(future_to_item):
                            item = future_to_item[future]
                            try:
                                item_processed, item_path = future.result()
                                if item_processed and item_processed not in processed:
                                    processed.extend(item_processed)
                                if item_path:
                                    path_list.append(item_path)
                            except Exception as e:
                                logger.error(
                                    f"【全量STRM生成】并发处理出错: {item} - {str(e)}"
                                )

                    self.fullsyncdbcacher.upsert_batch(processed)

                    if self.remove_unless_strm:
                        tree.generate_tree_from_list(
                            path_list, self.pan_tree, append=True
                        )

            except Exception as e:
                logger.error(f"【全量STRM生成】全量生成 STRM 文件失败: {e}")
                return False

            if self.remove_unless_strm:
                while local_tree_task_thread.is_alive():
                    logger.info("【全量STRM生成】扫描本地媒体库运行中...")
                    time.sleep(10)
                if not self.strm_fail_dict:
                    try:
                        for path in tree.compare_trees(self.local_tree, self.pan_tree):
                            logger.info(f"【全量STRM生成】清理无效 STRM 文件: {path}")
                            Path(path).unlink(missing_ok=True)
                            self.__remove_parent_dir(file_path=Path(path))
                            self.remove_unless_strm_count += 1
                    except Exception as e:
                        logger.error(f"【全量STRM生成】清理无效 STRM 文件失败: {e}")
                else:
                    logger.warn(
                        "【全量STRM生成】存在生成失败的 STRM 文件，跳过清理无效 STRM 文件"
                    )

        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict = (
            self.mediainfodownloader.auto_downloader(
                downloads_list=self.download_mediainfo_list
            )
        )
        if self.strm_fail_dict:
            for path, error in self.strm_fail_dict.items():
                logger.warn(f"【全量STRM生成】{path} 生成错误原因: {error}")
        if self.mediainfo_fail_dict:
            for path in self.mediainfo_fail_dict:
                logger.warn(f"【全量STRM生成】{path} 下载错误")
        logger.info(
            f"【全量STRM生成】全量生成 STRM 文件完成，总共生成 {self.strm_count} 个 STRM 文件，下载 {self.mediainfo_count} 个媒体数据文件"
        )
        if self.strm_fail_count != 0 or self.mediainfo_fail_count != 0:
            logger.warn(
                f"【全量STRM生成】{self.strm_fail_count} 个 STRM 文件生成失败，{self.mediainfo_fail_count} 个媒体数据文件下载失败"
            )
        if self.remove_unless_strm_count != 0:
            logger.warn(
                f"【全量STRM生成】清理 {self.remove_unless_strm_count} 个失效 STRM 文件"
            )

        # logger.debug(
        #     f"【全量STRM生成】时间 {elapsed_time:.6f} 秒，总迭代文件数量 {self.total_count} 个"
        # )

        return True

    def get_generate_total(self):
        """
        输出总共生成文件个数
        """
        return (
            self.strm_count,
            self.mediainfo_count,
            self.strm_fail_count,
            self.mediainfo_fail_count,
            self.remove_unless_strm_count,
        )


class ShareStrmHelper:
    """
    根据分享生成STRM
    """

    def __init__(self, client: P115Client, mediainfodownloader: MediaInfoDownloader):
        self.rmt_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_rmt_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.download_mediaext = [
            f".{ext.strip()}"
            for ext in configer.get_config("user_download_mediaext")
            .replace("，", ",")
            .split(",")
        ]
        self.auto_download_mediainfo = configer.get_config(
            "share_strm_auto_download_mediainfo_enabled"
        )
        self.client = client
        self.mediainfodownloader = mediainfodownloader
        self.strm_count = 0
        self.strm_fail_count = 0
        self.mediainfo_count = 0
        self.mediainfo_fail_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = None
        self.share_media_path = configer.get_config("user_share_pan_path")
        self.local_media_path = configer.get_config("user_share_local_path")
        self.server_address = configer.get_config("moviepilot_address").rstrip("/")
        self.strm_url_format = configer.get_config("strm_url_format")
        self.download_mediainfo_list = []

    def generate_strm_files(
        self,
        share_code: str,
        receive_code: str,
        file_id: str,
        file_path: str,
        pan_file_name: str,
    ):
        """
        生成 STRM 文件
        """
        if not PathUtils.has_prefix(file_path, self.share_media_path):
            logger.debug(
                "【分享STRM生成】此文件不在用户设置分享目录下，跳过网盘路径: %s",
                str(file_path).replace(str(self.local_media_path), "", 1),
            )
            return
        file_path = Path(self.local_media_path) / Path(file_path).relative_to(
            self.share_media_path
        )
        file_target_dir = file_path.parent
        original_file_name = file_path.name
        file_name = file_path.stem + ".strm"
        new_file_path = file_target_dir / file_name
        try:
            if self.auto_download_mediainfo:
                if file_path.suffix in self.download_mediaext:
                    self.download_mediainfo_list.append(
                        {
                            "type": "share",
                            "share_code": share_code,
                            "receive_code": receive_code,
                            "file_id": file_id,
                            "path": file_path,
                        }
                    )
                    return

            if file_path.suffix not in self.rmt_mediaext:
                logger.warn(
                    "【分享STRM生成】文件后缀不匹配，跳过网盘路径: %s",
                    str(file_path).replace(str(self.local_media_path), "", 1),
                )
                return

            new_file_path.parent.mkdir(parents=True, exist_ok=True)

            if not file_id:
                logger.error(
                    f"【分享STRM生成】{original_file_name} 不存在 id 值，无法生成 STRM 文件"
                )
                self.strm_fail_dict[str(new_file_path)] = "不存在 id 值"
                self.strm_fail_count += 1
                return
            if not share_code:
                logger.error(
                    f"【分享STRM生成】{original_file_name} 不存在 share_code 值，无法生成 STRM 文件"
                )
                self.strm_fail_dict[str(new_file_path)] = "不存在 share_code 值"
                self.strm_fail_count += 1
                return
            if not receive_code:
                logger.error(
                    f"【分享STRM生成】{original_file_name} 不存在 receive_code 值，无法生成 STRM 文件"
                )
                self.strm_fail_dict[str(new_file_path)] = "不存在 receive_code 值"
                self.strm_fail_count += 1
                return
            strm_url = f"{self.server_address}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&share_code={share_code}&receive_code={receive_code}&id={file_id}"
            if self.strm_url_format == "pickname":
                strm_url += f"&file_name={pan_file_name}"

            with open(new_file_path, "w", encoding="utf-8") as file:
                file.write(strm_url)
            self.strm_count += 1
            logger.info("【分享STRM生成】生成 STRM 文件成功: %s", str(new_file_path))
        except Exception as e:
            logger.error(
                "【分享STRM生成】生成 STRM 文件失败: %s  %s",
                str(new_file_path),
                e,
            )
            self.strm_fail_count += 1
            self.strm_fail_dict[str(new_file_path)] = str(e)
            return

    def get_share_list_creata_strm(
        self,
        cid: int = 0,
        current_path: str = "",
        share_code: str = "",
        receive_code: str = "",
    ):
        """
        获取分享文件，生成 STRM
        """
        for item in share_iterdir(
            self.client, receive_code=receive_code, share_code=share_code, cid=int(cid)
        ):
            item_path = (
                f"{current_path}/{item['name']}" if current_path else "/" + item["name"]
            )

            if item["is_dir"]:
                if self.strm_count != 0 and self.strm_count % 100 == 0:
                    logger.info("【分享STRM生成】休眠 1s 后继续生成")
                    time.sleep(1)
                self.get_share_list_creata_strm(
                    cid=int(item["id"]),
                    current_path=item_path,
                    share_code=share_code,
                    receive_code=receive_code,
                )
            else:
                item_with_path = dict(item)
                item_with_path["path"] = item_path
                self.generate_strm_files(
                    share_code=share_code,
                    receive_code=receive_code,
                    file_id=item_with_path["id"],
                    file_path=item_with_path["path"],
                    pan_file_name=item_with_path["name"],
                )

    def download_mediainfo(self):
        """
        下载媒体信息文件
        """
        self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict = (
            self.mediainfodownloader.auto_downloader(
                downloads_list=self.download_mediainfo_list
            )
        )

    def get_generate_total(self):
        """
        输出总共生成文件个数
        """
        if self.strm_fail_dict:
            for path, error in self.strm_fail_dict.items():
                logger.warn(f"【分享STRM生成】{path} 生成错误原因: {error}")
        if self.mediainfo_fail_dict:
            for path in self.mediainfo_fail_dict:
                logger.warn(f"【分享STRM生成】{path} 下载错误")
        logger.info(
            f"【分享STRM生成】分享生成 STRM 文件完成，总共生成 {self.strm_count} 个 STRM 文件，下载 {self.mediainfo_count} 个媒体数据文件"
        )
        if self.strm_fail_count != 0 or self.mediainfo_fail_count != 0:
            logger.warn(
                f"【分享STRM生成】{self.strm_fail_count} 个 STRM 文件生成失败，{self.mediainfo_fail_count} 个媒体数据文件下载失败"
            )
        return (
            self.strm_count,
            self.mediainfo_count,
            self.strm_fail_count,
            self.mediainfo_fail_count,
        )


class TransferStrmHelper:
    """
    处理事件事件STRM文件生成
    """

    @property
    def transfer_service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        监控MP整理 媒体服务器服务信息
        """
        if not configer.get_config("transfer_monitor_mediaservers"):
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        mediaserver_helper = MediaServerHelper()

        services = mediaserver_helper.get_services(
            name_filters=configer.get_config("transfer_monitor_mediaservers")
        )
        if not services:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(f"媒体服务器 {service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的媒体服务器，请检查配置")
            return None

        return active_services

    def refresh_media_server(self, item_dest_name: str, strm_target_path, mediainfo):
        """
        刷新媒体服务器
        """
        if not self.transfer_service_infos:
            return

        logger.info(f"【监控整理STRM生成】 {item_dest_name} 开始刷新媒体服务器")

        if configer.get_config("transfer_mp_mediaserver_paths"):
            status, mediaserver_path, moviepilot_path = PathUtils.get_media_path(
                configer.get_config("transfer_mp_mediaserver_paths"),
                strm_target_path,
            )
            if status:
                logger.info(
                    f"【监控整理STRM生成】 {item_dest_name} 刷新媒体服务器目录替换中..."
                )
                strm_target_path = strm_target_path.replace(
                    moviepilot_path, mediaserver_path
                ).replace("\\", "/")
                logger.info(
                    f"【监控整理STRM生成】刷新媒体服务器目录替换: {moviepilot_path} --> {mediaserver_path}"
                )
                logger.info(
                    f"【监控整理STRM生成】刷新媒体服务器目录: {strm_target_path}"
                )
        items = [
            RefreshMediaItem(
                title=mediainfo.title,
                year=mediainfo.year,
                type=mediainfo.type,
                category=mediainfo.category,
                target_path=Path(strm_target_path),
            )
        ]
        for name, service in self.transfer_service_infos.items():
            if hasattr(service.instance, "refresh_library_by_items"):
                service.instance.refresh_library_by_items(items)
            elif hasattr(service.instance, "refresh_root_library"):
                service.instance.refresh_root_library()
            else:
                logger.warning(
                    f"【监控整理STRM生成】 {item_dest_name} {name} 不支持刷新"
                )

    def generate_strm_files(
        self,
        target_dir: Path,
        pan_media_dir: Path,
        item_dest_path: Path,
        basename: str,
        url: str,
    ):
        """
        依据网盘路径生成 STRM 文件
        """
        try:
            pan_media_dir = str(Path(pan_media_dir))
            pan_path = Path(item_dest_path).parent
            pan_path = str(Path(pan_path))
            if PathUtils.has_prefix(pan_path, pan_media_dir):
                pan_path = pan_path[len(pan_media_dir) :].lstrip("/").lstrip("\\")
            file_path = Path(target_dir) / pan_path
            file_name = basename + ".strm"
            new_file_path = file_path / file_name
            new_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(new_file_path, "w", encoding="utf-8") as file:
                file.write(url)
            logger.info(
                "【监控整理STRM生成】生成 STRM 文件成功: %s", str(new_file_path)
            )
            return True, str(new_file_path)
        except Exception as e:  # noqa: F841
            logger.error(
                "【监控整理STRM生成】生成 %s 文件失败: %s", str(new_file_path), e
            )
            return False, None

    def do_generate(self, item, mediainfodownloader: MediaInfoDownloader):
        """
        生成 STRM 操作
        """
        # 转移信息
        item_transfer: TransferInfo = item.get("transferinfo")
        # 媒体信息
        mediainfo: MediaInfo = item.get("mediainfo")
        # 元数据信息
        meta: MetaBase = item.get("meta")

        item_dest_storage = item_transfer.target_item.storage
        if item_dest_storage != "u115":
            return

        # 网盘目的地目录
        itemdir_dest_path = item_transfer.target_diritem.path
        # 网盘目的地路径（包含文件名称）
        item_dest_path = item_transfer.target_item.path
        # 网盘目的地文件名称
        item_dest_name = item_transfer.target_item.name
        # 网盘目的地文件名称（不包含后缀）
        item_dest_basename = item_transfer.target_item.basename
        # 网盘目的地文件 pickcode
        item_dest_pickcode = item_transfer.target_item.pickcode
        # 是否蓝光原盘
        item_bluray = SystemUtils.is_bluray_dir(Path(itemdir_dest_path))
        # 目标字幕文件清单
        subtitle_list = getattr(item_transfer, "subtitle_list_new", [])
        # 目标音频文件清单
        audio_list = getattr(item_transfer, "audio_list_new", [])

        __itemdir_dest_path, local_media_dir, pan_media_dir = PathUtils.get_media_path(
            configer.get_config("transfer_monitor_paths"), itemdir_dest_path
        )
        if not __itemdir_dest_path:
            logger.debug(
                f"【监控整理STRM生成】{item_dest_name} 路径匹配不符合，跳过整理"
            )
            return
        logger.debug("【监控整理STRM生成】匹配到网盘文件夹路径: %s", str(pan_media_dir))

        if item_bluray:
            logger.warning(
                f"【监控整理STRM生成】{item_dest_name} 为蓝光原盘，不支持生成 STRM 文件: {item_dest_path}"
            )
            return

        if not item_dest_pickcode:
            logger.error(
                f"【监控整理STRM生成】{item_dest_name} 不存在 pickcode 值，无法生成 STRM 文件"
            )
            return
        if not (len(item_dest_pickcode) == 17 and str(item_dest_pickcode).isalnum()):
            logger.error(
                f"【监控整理STRM生成】错误的 pickcode 值 {item_dest_name}，无法生成 STRM 文件"
            )
            return
        strm_url = f"{configer.get_config('moviepilot_address').rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={item_dest_pickcode}"
        if configer.get_config("strm_url_format") == "pickname":
            strm_url += f"&file_name={item_dest_name}"

        _databasehelper = FileDbHelper()
        _databasehelper.upsert_batch(
            _databasehelper.process_fileitem(fileitem=item_transfer.target_item)
        )

        status, strm_target_path = self.generate_strm_files(
            target_dir=local_media_dir,
            pan_media_dir=pan_media_dir,
            item_dest_path=item_dest_path,
            basename=item_dest_basename,
            url=strm_url,
        )
        if not status:
            return

        try:
            storagechain = StorageChain()
            if subtitle_list:
                logger.info("【监控整理STRM生成】开始下载字幕文件")
                for _path in subtitle_list:
                    fileitem = storagechain.get_file_item(
                        storage="u115", path=Path(_path)
                    )
                    _databasehelper.upsert_batch(
                        _databasehelper.process_fileitem(fileitem)
                    )
                    download_url = mediainfodownloader.get_download_url(
                        pickcode=fileitem.pickcode
                    )
                    if not download_url:
                        logger.error(
                            f"【监控整理STRM生成】{Path(_path).name} 下载链接获取失败，无法下载该文件"
                        )
                        continue
                    _file_path = Path(local_media_dir) / Path(_path).relative_to(
                        pan_media_dir
                    )
                    mediainfodownloader.save_mediainfo_file(
                        file_path=Path(_file_path),
                        file_name=_file_path.name,
                        download_url=download_url,
                    )

            if audio_list:
                logger.info("【监控整理STRM生成】开始下载音频文件")
                for _path in audio_list:
                    fileitem = storagechain.get_file_item(
                        storage="u115", path=Path(_path)
                    )
                    _databasehelper.upsert_batch(
                        _databasehelper.process_fileitem(fileitem)
                    )
                    download_url = mediainfodownloader.get_download_url(
                        pickcode=fileitem.pickcode
                    )
                    if not download_url:
                        logger.error(
                            f"【监控整理STRM生成】{Path(_path).name} 下载链接获取失败，无法下载该文件"
                        )
                        continue
                    _file_path = Path(local_media_dir) / Path(_path).relative_to(
                        pan_media_dir
                    )
                    mediainfodownloader.save_mediainfo_file(
                        file_path=Path(_file_path),
                        file_name=_file_path.name,
                        download_url=download_url,
                    )
        except Exception as e:
            logger.error(f"【监控整理STRM生成】媒体信息文件下载出现未知错误: {e}")

        scrape_metadata = True
        if configer.get_config("transfer_monitor_scrape_metadata_enabled"):
            if configer.get_config("transfer_monitor_scrape_metadata_exclude_paths"):
                if PathUtils.get_scrape_metadata_exclude_path(
                    configer.get_config(
                        "transfer_monitor_scrape_metadata_exclude_paths"
                    ),
                    str(strm_target_path),
                ):
                    logger.debug(
                        f"【监控整理STRM生成】匹配到刮削排除目录，不进行刮削: {strm_target_path}"
                    )
                    scrape_metadata = False
            if scrape_metadata:
                media_scrape_metadata(
                    path=strm_target_path,
                    item_name=item_dest_name,
                    mediainfo=mediainfo,
                    meta=meta,
                )

        if configer.get_config("transfer_monitor_media_server_refresh_enabled"):
            self.refresh_media_server(
                item_dest_name=item_dest_name,
                strm_target_path=strm_target_path,
                mediainfo=mediainfo,
            )
