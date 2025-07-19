import threading
import traceback
import shutil
import re
from pathlib import Path
from collections import defaultdict
from typing import Optional, Any

from watchdog.events import FileSystemEventHandler

from app.chain.storage import StorageChain
from app.log import logger
from app.utils.system import SystemUtils
from app.schemas import FileItem

from ..core.config import configer


directory_upload_dict = defaultdict(threading.Lock)


class FileMonitorHandler(FileSystemEventHandler):
    """
    目录监控响应类
    """

    def __init__(self, monpath: str, sync: Any, **kwargs):
        super(FileMonitorHandler, self).__init__(**kwargs)
        self._watch_path = monpath
        self.sync = sync

    def on_created(self, event):
        """
        创建
        """
        self.sync.event_handler(
            event=event,
            text="创建",
            mon_path=self._watch_path,
            event_path=event.src_path,
        )

    def on_moved(self, event):
        """
        移动
        """
        self.sync.event_handler(
            event=event,
            text="移动",
            mon_path=self._watch_path,
            event_path=event.dest_path,
        )


def handle_file(event_path: str, mon_path: str):
    """
    同步一个文件
    :param event_path: 事件文件路径
    :param mon_path: 监控目录
    """
    file_path = Path(event_path)
    storagechain = StorageChain()
    try:
        if not file_path.exists():
            return
        # 全程加锁
        with directory_upload_dict[str(file_path.absolute())]:
            # 回收站隐藏文件不处理
            if (
                event_path.find("/@Recycle/") != -1
                or event_path.find("/#recycle/") != -1
                or event_path.find("/.") != -1
                or event_path.find("/@eaDir") != -1
            ):
                logger.debug(f"【目录上传】{event_path} 是回收站或隐藏的文件")
                return

            # 蓝光目录不处理
            if re.search(r"BDMV[/\\]STREAM", event_path, re.IGNORECASE):
                return

            # 先判断文件是否存在
            file_item = storagechain.get_file_item(storage="local", path=file_path)
            if not file_item:
                logger.warn(f"【目录上传】{event_path} 未找到对应的文件")
                return

            # 获取此监控目录配置
            for item in configer.get_config("directory_upload_path"):
                if not item:
                    continue
                if mon_path == item.get("src", ""):
                    delete = item.get("delete", False)
                    dest_remote = item.get("dest_remote", "")
                    dest_local = item.get("dest_local", "")
                    break

            if file_path.suffix in [
                f".{ext.strip()}"
                for ext in configer.get_config("directory_upload_uploadext")
                .replace("，", ",")
                .split(",")
            ]:
                # 处理上传
                if not dest_remote:
                    logger.error(f"【目录上传】{file_path} 未找到对应的上传网盘目录")
                    return

                target_file_path = Path(dest_remote) / Path(file_path).relative_to(
                    mon_path
                )

                # 网盘目录创建流程
                def __find_dir(_fileitem: FileItem, _name: str) -> Optional[FileItem]:
                    """
                    查找下级目录中匹配名称的目录
                    """
                    for sub_folder in storagechain.list_files(_fileitem):
                        if sub_folder.type != "dir":
                            continue
                        if sub_folder.name == _name:
                            return sub_folder
                    return None

                target_fileitem = storagechain.get_file_item(
                    storage="u115", path=target_file_path.parent
                )
                if not target_fileitem:
                    # 逐级查找和创建目录
                    target_fileitem = FileItem(storage="u115", path="/")
                    for part in target_file_path.parent.parts[1:]:
                        dir_file = __find_dir(target_fileitem, part)
                        if dir_file:
                            target_fileitem = dir_file
                        else:
                            dir_file = storagechain.create_folder(target_fileitem, part)
                            if not dir_file:
                                logger.error(
                                    f"【目录上传】创建目录 {target_fileitem.path}{part} 失败！"
                                )
                                return
                            target_fileitem = dir_file

                # 上传流程
                if storagechain.upload_file(target_fileitem, file_path, file_path.name):
                    logger.info(
                        f"【目录上传】{file_path} 上传到网盘 {target_file_path} 成功 "
                    )
                else:
                    logger.error(f"【目录上传】{file_path} 上传网盘失败")
                    return

            elif file_path.suffix in [
                f".{ext.strip()}"
                for ext in configer.get_config("directory_upload_copyext")
                .replace("，", ",")
                .split(",")
            ]:
                # 处理非上传文件
                if dest_local:
                    target_file_path = Path(dest_local) / Path(file_path).relative_to(
                        mon_path
                    )
                    # 创建本地目录
                    target_file_path.parent.mkdir(parents=True, exist_ok=True)
                    # 复制文件
                    status, msg = SystemUtils.copy(file_path, target_file_path)
                    if status == 0:
                        logger.info(
                            f"【目录上传】{file_path} 复制到 {target_file_path} 成功 "
                        )
                    else:
                        logger.error(f"【目录上传】{file_path} 复制失败: {msg}")
                        return
            else:
                # 未匹配后缀的文件直接跳过
                return

            # 处理源文件是否删除
            if delete:
                logger.info(f"【目录上传】删除源文件：{file_path}")
                file_path.unlink(missing_ok=True)
                for file_dir in file_path.parents:
                    if len(str(file_dir)) <= len(str(Path(mon_path))):
                        break
                    files = SystemUtils.list_files(file_dir)
                    if not files:
                        logger.warn(f"【目录上传】删除空目录：{file_dir}")
                        shutil.rmtree(file_dir, ignore_errors=True)

    except Exception as e:
        logger.error(
            f"【目录上传】目录监控发生错误：{str(e)} - {traceback.format_exc()}"
        )
        return
