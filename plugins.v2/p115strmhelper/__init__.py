import threading
import time
import shutil
import base64
import re
from threading import Event as ThreadEvent, Timer
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Self, cast, Optional
from errno import EIO, ENOENT
from urllib.parse import quote, unquote, urlsplit, urlencode
from itertools import chain, batched
from pathlib import Path
from functools import wraps

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Request, Response
import requests
from requests.exceptions import HTTPError
from orjson import dumps, loads
from cachetools import cached, TTLCache, LRUCache
from p115client import P115Client
from p115client.exception import DataError
from p115client.tool.iterdir import iter_files_with_path, get_path_to_cid, share_iterdir
from p115client.tool.life import iter_life_behavior_list, life_show
from p115client.tool.util import share_extract_payload
from p115rsacipher import encrypt, decrypt

from .db_manager import ct_db_manager
from .db_manager.init import init_db, update_db
from .db_manager.oper import FileDbHelper

from app import schemas
from app.schemas import (
    TransferInfo,
    FileItem,
    RefreshMediaItem,
    ServiceInfo,
    NotificationType,
)
from app.schemas.types import EventType, MediaType
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.core.context import MediaInfo
from app.core.meta import MetaBase
from app.core.metainfo import MetaInfoPath
from app.log import logger
from app.plugins import _PluginBase
from app.chain.transfer import TransferChain
from app.chain.media import MediaChain
from app.helper.mediaserver import MediaServerHelper
from app.utils.system import SystemUtils


p115strmhelper_lock = threading.Lock()


def check_response(
    resp: requests.Response,
) -> requests.Response:
    """
    检查 HTTP 响应，如果状态码 ≥ 400 则抛出 HTTPError
    """
    if resp.status_code >= 400:
        raise HTTPError(
            f"HTTP Error {resp.status_code}: {resp.text}",
            response=resp,
        )
    return resp


class PathMatchingHelper:
    """
    路径匹配
    """

    def has_prefix(self, full_path, prefix_path):
        """
        判断路径是否包含
        :param full_path: 完整路径
        :param prefix_path: 匹配路径
        """
        full = Path(full_path).parts
        prefix = Path(prefix_path).parts

        if len(prefix) > len(full):
            return False

        return full[: len(prefix)] == prefix

    def get_run_transfer_path(self, paths, transfer_path):
        """
        判断路径是否为整理路径
        """
        transfer_paths = paths.split("\n")
        for path in transfer_paths:
            if not path:
                continue
            if self.has_prefix(transfer_path, path):
                return True
        return False

    def get_scrape_metadata_exclude_path(self, paths, scrape_path):
        """
        检查目录是否在排除目录内
        """
        exclude_path = paths.split("\n")
        for path in exclude_path:
            if not path:
                continue
            if self.has_prefix(scrape_path, path):
                return True
        return False

    def get_media_path(self, paths, media_path):
        """
        获取媒体目录路径
        """
        media_paths = paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 1)
            if self.has_prefix(media_path, parts[1]):
                return True, parts[0], parts[1]
        return False, None, None


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


class Url(str):
    def __new__(cls, val: Any = "", /, *args, **kwds):
        return super().__new__(cls, val)

    def __init__(self, val: Any = "", /, *args, **kwds):
        self.__dict__.update(*args, **kwds)

    def __getattr__(self, attr: str, /):
        try:
            return self.__dict__[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    def __getitem__(self, key, /):
        try:
            if isinstance(key, str):
                return self.__dict__[key]
        except KeyError:
            return super().__getitem__(key)  # type: ignore

    def __repr__(self, /) -> str:
        cls = type(self)
        if (module := cls.__module__) == "__main__":
            name = cls.__qualname__
        else:
            name = f"{module}.{cls.__qualname__}"
        return f"{name}({super().__repr__()}, {self.__dict__!r})"

    @classmethod
    def of(cls, val: Any = "", /, ns: None | dict = None) -> Self:
        self = cls.__new__(cls, val)
        if ns is not None:
            self.__dict__ = ns
        return self

    def get(self, key, /, default=None):
        return self.__dict__.get(key, default)

    def items(self, /):
        return self.__dict__.items()

    def keys(self, /):
        return self.__dict__.keys()

    def values(self, /):
        return self.__dict__.values()


class MediaInfoDownloader:
    """
    媒体信息文件下载器
    """

    def __init__(self, cookie: str):
        self.cookie = cookie

    def is_file_leq_1k(self, file_path):
        """
        判断文件是否小于 1KB
        """
        file = Path(file_path)
        if not file.exists():
            return True
        return file.stat().st_size <= 1024

    def get_download_url(self, pickcode: str):
        """
        获取下载链接
        """
        resp = requests.post(
            "http://proapi.115.com/android/2.0/ufile/download",
            data={"data": encrypt(f'{{"pick_code":"{pickcode}"}}').decode("utf-8")},
            headers={
                "User-Agent": settings.USER_AGENT,
                "Cookie": self.cookie,
            },
        )
        check_response(resp)
        json = loads(cast(bytes, resp.content))
        if not json["state"]:
            raise OSError(EIO, json)
        data = json["data"] = loads(decrypt(json["data"]))
        data["file_name"] = unquote(urlsplit(data["url"]).path.rpartition("/")[-1])
        return Url.of(data["url"], data)

    def save_mediainfo_file(self, file_path: Path, file_name: str, download_url: str):
        """
        保存媒体信息文件
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(
            download_url,
            stream=True,
            timeout=30,
            headers={
                "User-Agent": settings.USER_AGENT,
                "Cookie": self.cookie,
            },
        ) as response:
            response.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"【媒体信息文件下载】保存 {file_name} 文件成功: {file_path}")

    def local_downloader(self, pickcode: str, path: Path):
        """
        下载用户网盘文件
        """
        download_url = self.get_download_url(pickcode=pickcode)
        if not download_url:
            logger.error(
                f"【媒体信息文件下载】{path.name} 下载链接获取失败，无法下载该文件"
            )
            return
        self.save_mediainfo_file(
            file_path=path,
            file_name=path.name,
            download_url=download_url,
        )

    def share_downloader(
        self, share_code: str, receive_code: str, file_id: str, path: Path
    ):
        """
        下载分享链接文件
        """
        payload = {
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": file_id,
        }
        resp = requests.post(
            "http://proapi.115.com/app/share/downurl",
            data={"data": encrypt(dumps(payload)).decode("utf-8")},
            headers={
                "User-Agent": settings.USER_AGENT,
                "Cookie": self.cookie,
            },
        )
        check_response(resp)
        json = loads(cast(bytes, resp.content))
        if not json["state"]:
            raise OSError(EIO, json)
        data = json["data"] = loads(decrypt(json["data"]))
        if not (data and (url_info := data["url"])):
            raise FileNotFoundError(ENOENT, json)
        data["file_id"] = data.pop("fid")
        data["file_name"] = data.pop("fn")
        data["file_size"] = int(data.pop("fs"))
        download_url = Url.of(url_info["url"], data)
        if not download_url:
            logger.error(
                f"【媒体信息文件下载】{path.name} 下载链接获取失败，无法下载该文件"
            )
            return
        self.save_mediainfo_file(
            file_path=path,
            file_name=path.name,
            download_url=download_url,
        )

    def auto_downloader(self, downloads_list: List):
        """
        根据列表自动下载
        """
        mediainfo_count: int = 0
        mediainfo_fail_count: int = 0
        mediainfo_fail_dict: List = []
        try:
            for item in downloads_list:
                if not item:
                    continue
                download_success = False
                if item["type"] == "local":
                    try:
                        for _ in range(3):
                            self.local_downloader(
                                pickcode=item["pickcode"], path=Path(item["path"])
                            )
                            if not self.is_file_leq_1k(item["path"]):
                                mediainfo_count += 1
                                download_success = True
                                break
                            logger.warn(
                                f"【媒体信息文件下载】{item['path']} 下载该文件失败，自动重试"
                            )
                            time.sleep(1)
                    except Exception as e:
                        logger.error(
                            f"【媒体信息文件下载】 {item['path']} 出现未知错误: {e}"
                        )
                    if not download_success:
                        mediainfo_fail_count += 1
                        mediainfo_fail_dict.append(item["path"])
                elif item["type"] == "share":
                    try:
                        for _ in range(3):
                            self.share_downloader(
                                share_code=item["share_code"],
                                receive_code=item["receive_code"],
                                file_id=item["file_id"],
                                path=Path(item["path"]),
                            )
                            if not self.is_file_leq_1k(item["path"]):
                                mediainfo_count += 1
                                download_success = True
                                break
                            logger.warn(
                                f"【媒体信息文件下载】{item['path']} 下载该文件失败，自动重试"
                            )
                            time.sleep(1)
                    except Exception as e:
                        logger.error(
                            f"【媒体信息文件下载】 {item['path']} 出现未知错误: {e}"
                        )
                    if not download_success:
                        mediainfo_fail_count += 1
                        mediainfo_fail_dict.append(item["path"])
                else:
                    continue
                if mediainfo_count % 50 == 0:
                    logger.info("【媒体信息文件下载】休眠 2s 后继续下载")
                    time.sleep(2)
        except Exception as e:
            logger.error(f"【媒体信息文件下载】出现未知错误: {e}")
        return mediainfo_count, mediainfo_fail_count, mediainfo_fail_dict


class FullSyncStrmHelper:
    """
    全量生成 STRM 文件
    """

    def __init__(
        self,
        client,
        user_rmt_mediaext: str,
        user_download_mediaext: str,
        server_address: str,
        pan_transfer_enabled: bool,
        pan_transfer_paths: str,
        strm_url_format: str,
        mediainfodownloader: MediaInfoDownloader,
        auto_download_mediainfo: bool = False,
    ):
        self.rmt_mediaext = [
            f".{ext.strip()}" for ext in user_rmt_mediaext.replace("，", ",").split(",")
        ]
        self.download_mediaext = [
            f".{ext.strip()}"
            for ext in user_download_mediaext.replace("，", ",").split(",")
        ]
        self.auto_download_mediainfo = auto_download_mediainfo
        self.client = client
        self.strm_count = 0
        self.mediainfo_count = 0
        self.strm_fail_count = 0
        self.mediainfo_fail_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = None
        self.server_address = server_address.rstrip("/")
        self.pan_transfer_enabled = pan_transfer_enabled
        self.pan_transfer_paths = pan_transfer_paths
        self.strm_url_format = strm_url_format
        self.databasehelper = FileDbHelper()
        self.pathmatchinghelper = PathMatchingHelper()
        self.mediainfodownloader = mediainfodownloader
        self.download_mediainfo_list = []

    def generate_strm_files(self, full_sync_strm_paths):
        """
        生成 STRM 文件
        """
        media_paths = full_sync_strm_paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 1)
            pan_media_dir = parts[1]
            target_dir = parts[0]

            try:
                parent_id = int(self.client.fs_dir_getid(pan_media_dir)["id"])
                logger.info(f"【全量STRM生成】网盘媒体目录 ID 获取成功: {parent_id}")
            except Exception as e:
                logger.error(f"【全量STRM生成】网盘媒体目录 ID 获取失败: {e}")
                return False

            try:
                for batch in batched(
                    iter_files_with_path(self.client, cid=parent_id, cooldown=2), 7_000
                ):
                    processed = []
                    for item in batch:
                        _process_item = self.databasehelper.process_item(item)
                        if _process_item not in processed:
                            processed.extend(_process_item)
                        if item["is_dir"] or item["is_directory"]:
                            continue
                        file_path = item["path"]
                        file_path = Path(target_dir) / Path(file_path).relative_to(
                            pan_media_dir
                        )
                        file_target_dir = file_path.parent
                        original_file_name = file_path.name
                        file_name = file_path.stem + ".strm"
                        new_file_path = file_target_dir / file_name
                        try:
                            if self.pan_transfer_enabled and self.pan_transfer_paths:
                                if self.pathmatchinghelper.get_run_transfer_path(
                                    paths=self.pan_transfer_paths,
                                    transfer_path=item["path"],
                                ):
                                    logger.debug(
                                        f"【全量STRM生成】{item['path']} 为待整理目录下的路径，不做处理"
                                    )
                                    continue

                            if self.auto_download_mediainfo:
                                if file_path.suffix in self.download_mediaext:
                                    pickcode = item["pickcode"]
                                    if not pickcode:
                                        logger.error(
                                            f"【全量STRM生成】{original_file_name} 不存在 pickcode 值，无法下载该文件"
                                        )
                                        continue
                                    self.download_mediainfo_list.append(
                                        {
                                            "type": "local",
                                            "pickcode": pickcode,
                                            "path": file_path,
                                        }
                                    )
                                    continue

                            if file_path.suffix not in self.rmt_mediaext:
                                logger.warn(
                                    "【全量STRM生成】跳过网盘路径: %s",
                                    str(file_path).replace(str(target_dir), "", 1),
                                )
                                continue

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
                                continue
                            if not (len(pickcode) == 17 and str(pickcode).isalnum()):
                                self.strm_fail_count += 1
                                self.strm_fail_dict[str(new_file_path)] = (
                                    f"错误的 pickcode 值 {pickcode}"
                                )
                                logger.error(
                                    f"【全量STRM生成】错误的 pickcode 值 {pickcode}，无法生成 STRM 文件"
                                )
                                continue
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
                        except Exception as e:
                            logger.error(
                                "【全量STRM生成】生成 STRM 文件失败: %s  %s",
                                str(new_file_path),
                                e,
                            )
                            self.strm_fail_count += 1
                            self.strm_fail_dict[str(new_file_path)] = str(e)
                            continue
                    self.databasehelper.upsert_batch(processed)
            except Exception as e:
                logger.error(f"【全量STRM生成】全量生成 STRM 文件失败: {e}")
                return False
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
        )


class ShareStrmHelper:
    """
    根据分享生成STRM
    """

    def __init__(
        self,
        client,
        user_rmt_mediaext: str,
        user_download_mediaext: str,
        share_media_path: str,
        local_media_path: str,
        server_address: str,
        mediainfodownloader: MediaInfoDownloader,
        auto_download_mediainfo: bool = False,
    ):
        self.rmt_mediaext = [
            f".{ext.strip()}" for ext in user_rmt_mediaext.replace("，", ",").split(",")
        ]
        self.download_mediaext = [
            f".{ext.strip()}"
            for ext in user_download_mediaext.replace("，", ",").split(",")
        ]
        self.auto_download_mediainfo = auto_download_mediainfo
        self.client = client
        self.strm_count = 0
        self.strm_fail_count = 0
        self.mediainfo_count = 0
        self.mediainfo_fail_count = 0
        self.strm_fail_dict: Dict[str, str] = {}
        self.mediainfo_fail_dict: List = None
        self.share_media_path = share_media_path
        self.local_media_path = local_media_path
        self.server_address = server_address.rstrip("/")
        self.pathmatchinghelper = PathMatchingHelper()
        self.mediainfodownloader = mediainfodownloader
        self.download_mediainfo_list = []

    def generate_strm_files(
        self,
        share_code: str,
        receive_code: str,
        file_id: str,
        file_path: str,
    ):
        """
        生成 STRM 文件
        """
        if not self.pathmatchinghelper.has_prefix(file_path, self.share_media_path):
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

            if item["is_directory"] or item["is_dir"]:
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


class P115StrmHelper(_PluginBase):
    # 插件名称
    plugin_name = "115网盘STRM助手"
    # 插件描述
    plugin_desc = "115网盘STRM生成一条龙服务"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Frontend/refs/heads/v2/src/assets/images/misc/u115.png"
    # 插件版本
    plugin_version = "1.6.12"
    # 插件作者
    plugin_author = "DDSRem"
    # 作者主页
    author_url = "https://github.com/DDSRem"
    # 插件配置项ID前缀
    plugin_config_prefix = "p115strmhelper_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    mediaserver_helper = None
    transferchain = None
    mediachain = None
    pathmatchinghelper = None
    mediainfodownloader = None

    # 目录ID缓存
    id_path_cache = None
    # 生活事件缓存
    cache_delete_pan_transfer_list = None
    cache_creata_pan_transfer_list = None
    cache_top_delete_pan_transfer_list = None

    # 生活事件监控通知系统
    _monitor_life_notification_queue = None
    _monitor_life_notification_timer = None

    _client = None
    _scheduler = None
    _enabled = False
    _notify = False
    _strm_url_format = None
    _cookies = None
    _password = None
    moviepilot_address = None
    _user_rmt_mediaext = None
    _user_download_mediaext = None
    _transfer_monitor_enabled = False
    _transfer_monitor_scrape_metadata_enabled = False
    _transfer_monitor_scrape_metadata_exclude_paths = None
    _transfer_monitor_paths = None
    _transfer_mp_mediaserver_paths = None
    _transfer_monitor_mediaservers = None
    _transfer_monitor_media_server_refresh_enabled = False
    _timing_full_sync_strm = False
    _full_sync_auto_download_mediainfo_enabled = False
    _cron_full_sync_strm = None
    _full_sync_strm_paths = None
    _mediaservers = None
    _monitor_life_enabled = False
    _monitor_life_auto_download_mediainfo_enabled = False
    _monitor_life_paths = None
    _monitor_life_mp_mediaserver_paths = None
    _monitor_life_media_server_refresh_enabled = False
    _monitor_life_mediaservers = None
    _monitor_life_auto_remove_local_enabled = False
    _monitor_life_scrape_metadata_enabled = False
    _monitor_life_scrape_metadata_exclude_paths = None
    _share_strm_auto_download_mediainfo_enabled = False
    _user_share_code = None
    _user_receive_code = None
    _user_share_link = None
    _user_share_pan_path = None
    _user_share_local_path = None
    _clear_recyclebin_enabled = False
    _clear_receive_path_enabled = False
    _cron_clear = None
    _pan_transfer_enabled = False
    _pan_transfer_paths = None
    # 退出事件
    _event = ThreadEvent()
    monitor_stop_event = None
    monitor_life_thread = None

    @staticmethod
    def logs_oper(oper_name: str):
        """
        数据库操作汇报装饰器
        - 捕获异常并记录日志
        - 5秒内合并多条消息，避免频繁发送通知
        """

        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                level, text = "success", f"{oper_name} 成功"
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"{oper_name} 失败：{str(e)}", exc_info=True)
                    level, text = "error", f"{oper_name} 失败：{str(e)}"
                    return False
                finally:
                    if hasattr(self, "add_message"):
                        self.add_message(title=oper_name, text=text, level=level)

            return wrapper

        return decorator

    def __init__(self):
        """
        初始化
        """
        super().__init__()
        # 类名小写
        class_name = self.__class__.__name__.lower()
        # 插件配置文件路径
        self.__plugin_config_path = settings.PLUGIN_DATA_PATH / class_name
        # 数据库文件路径
        self.__db_path = (
            settings.PLUGIN_DATA_PATH / class_name / "p115strmhelper_file.db"
        )
        self.__database_path = (
            settings.ROOT_PATH / "app/plugins" / class_name / "database"
        )
        self.init_database()

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        self.mediaserver_helper = MediaServerHelper()
        self.transferchain = TransferChain()
        self.mediachain = MediaChain()
        self.pathmatchinghelper = PathMatchingHelper()
        self.monitor_stop_event = threading.Event()

        self.id_path_cache = IdPathCache()
        self.cache_delete_pan_transfer_list = []
        self.cache_creata_pan_transfer_list = []
        self.cache_top_delete_pan_transfer_list: Dict[str, List] = {}

        self._monitor_life_notification_queue = defaultdict(
            lambda: {"strm_count": 0, "mediainfo_count": 0}
        )
        self._monitor_life_notification_timer = None

        if config:
            self._enabled = config.get("enabled", False)
            self._notify = config.get("notify", False)
            self._strm_url_format = config.get("strm_url_format", "pickcode")
            self._cookies = config.get("cookies")
            self._password = config.get("password")
            self.moviepilot_address = config.get("moviepilot_address")
            self._user_rmt_mediaext = config.get(
                "user_rmt_mediaext",
                "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
            )
            self._user_download_mediaext = config.get(
                "user_download_mediaext", "srt,ssa,ass"
            )
            self._transfer_monitor_enabled = config.get(
                "transfer_monitor_enabled", False
            )
            self._transfer_monitor_scrape_metadata_enabled = config.get(
                "transfer_monitor_scrape_metadata_enabled", False
            )
            self._transfer_monitor_scrape_metadata_exclude_paths = config.get(
                "transfer_monitor_scrape_metadata_exclude_paths"
            )
            self._transfer_monitor_paths = config.get("transfer_monitor_paths")
            self._transfer_mp_mediaserver_paths = config.get(
                "transfer_mp_mediaserver_paths"
            )
            self._transfer_monitor_mediaservers = config.get(
                "transfer_monitor_mediaservers"
            )
            self._transfer_monitor_media_server_refresh_enabled = config.get(
                "transfer_monitor_media_server_refresh_enabled", False
            )
            self._timing_full_sync_strm = config.get("timing_full_sync_strm", False)
            self._full_sync_auto_download_mediainfo_enabled = config.get(
                "full_sync_auto_download_mediainfo_enabled", False
            )
            self._cron_full_sync_strm = config.get("cron_full_sync_strm", "0 */7 * * *")
            self._full_sync_strm_paths = config.get("full_sync_strm_paths")
            self._monitor_life_enabled = config.get("monitor_life_enabled", False)
            self._monitor_life_auto_download_mediainfo_enabled = config.get(
                "monitor_life_auto_download_mediainfo_enabled", False
            )
            self._monitor_life_paths = config.get("monitor_life_paths")
            self._monitor_life_mp_mediaserver_paths = config.get(
                "monitor_life_mp_mediaserver_paths"
            )
            self._monitor_life_media_server_refresh_enabled = config.get(
                "monitor_life_media_server_refresh_enabled", False
            )
            self._monitor_life_mediaservers = config.get("monitor_life_mediaservers")
            self._monitor_life_auto_remove_local_enabled = config.get(
                "monitor_life_auto_remove_local_enabled", False
            )
            self._monitor_life_scrape_metadata_enabled = config.get(
                "monitor_life_scrape_metadata_enabled", False
            )
            self._monitor_life_scrape_metadata_exclude_paths = config.get(
                "monitor_life_scrape_metadata_exclude_paths"
            )
            self._share_strm_auto_download_mediainfo_enabled = config.get(
                "share_strm_auto_download_mediainfo_enabled", False
            )
            self._user_share_code = config.get("user_share_code")
            self._user_receive_code = config.get("user_receive_code")
            self._user_share_link = config.get("user_share_link")
            self._user_share_pan_path = config.get("user_share_pan_path")
            self._user_share_local_path = config.get("user_share_local_path")
            self._clear_recyclebin_enabled = config.get(
                "clear_recyclebin_enabled", False
            )
            self._clear_receive_path_enabled = config.get(
                "clear_receive_path_enabled", False
            )
            self._cron_clear = config.get("cron_clear", "0 */7 * * *")
            self._pan_transfer_enabled = config.get("pan_transfer_enabled", False)
            self._pan_transfer_paths = config.get("pan_transfer_paths")
            self.__update_config()

        # 停止现有任务
        self.stop_service()

        if self._enabled:
            self.init_database()

            try:
                self._client = P115Client(self._cookies)
                self.mediainfodownloader = MediaInfoDownloader(cookie=self._cookies)
            except Exception as e:
                logger.error(f"115网盘客户端创建失败: {e}")

            if (self._monitor_life_enabled and self._monitor_life_paths) or (
                self._pan_transfer_enabled and self._pan_transfer_paths
            ):
                self.monitor_stop_event.clear()
                if self.monitor_life_thread:
                    if not self.monitor_life_thread.is_alive():
                        self.monitor_life_thread = threading.Thread(
                            target=self.monitor_life_strm_files, daemon=True
                        )
                        self.monitor_life_thread.start()
                else:
                    self.monitor_life_thread = threading.Thread(
                        target=self.monitor_life_strm_files, daemon=True
                    )
                    self.monitor_life_thread.start()

    @logs_oper("初始化数据库")
    def init_database(self) -> bool:
        """
        初始化数据库
        """
        if not Path(self.__plugin_config_path).exists():
            Path(self.__plugin_config_path).mkdir(parents=True, exist_ok=True)
        if not ct_db_manager.is_initialized():
            # 初始化数据库会话
            ct_db_manager.init_database(db_path=self.__db_path)
            # 表单补全
            init_db(
                engine=ct_db_manager.Engine,
            )
            # 更新数据库
            update_db(
                db_path=self.__db_path,
                database_dir=self.__database_path,
            )
        return True

    def get_state(self) -> bool:
        """
        插件状态
        """
        return self._enabled

    @property
    def transfer_service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        监控MP整理 媒体服务器服务信息
        """
        if not self._transfer_monitor_mediaservers:
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        services = self.mediaserver_helper.get_services(
            name_filters=self._transfer_monitor_mediaservers
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

    @property
    def monitor_life_service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        监控生活事件 媒体服务器服务信息
        """
        if not self._monitor_life_mediaservers:
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        services = self.mediaserver_helper.get_services(
            name_filters=self._monitor_life_mediaservers
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

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/p115_full_sync",
                "event": EventType.PluginAction,
                "desc": "全量同步115网盘文件",
                "category": "",
                "data": {"action": "p115_full_sync"},
            },
            {
                "cmd": "/p115_add_share",
                "event": EventType.PluginAction,
                "desc": "转存分享到待整理目录",
                "category": "",
                "data": {"action": "p115_add_share"},
            },
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """
        BASE_URL: {server_url}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={APIKEY}
        0. 查询 pickcode
            url: ${BASE_URL}&pickcode=ecjq9ichcb40lzlvx
        1. 带（任意）名字查询 pickcode
            url: ${BASE_URL}&file_name=Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv&pickcode=ecjq9ichcb40lzlvx
        2. 查询分享文件（如果是你自己的分享，则无须提供密码 receive_code）
            url: ${BASE_URL}&share_code=sw68md23w8m&receive_code=q353&id=2580033742990999218
            url: ${BASE_URL}&share_code=sw68md23w8m&id=2580033742990999218
        3. 用 file_name 查询分享文件（直接以路径作为 file_name，且不要有 id 查询参数。如果是你自己的分享，则无须提供密码 receive_code）
            url: ${BASE_URL}&file_name=Cosmos.S01E01.1080p.AMZN.WEB-DL.DD%2B5.1.H.264-iKA.mkv&share_code=sw68md23w8m&receive_code=q353
            url: ${BASE_URL}&file_name=Cosmos.S01E01.1080p.AMZN.WEB-DL.DD%2B5.1.H.264-iKA.mkv&share_code=sw68md23w8m
        """
        return [
            {
                "path": "/redirect_url",
                "endpoint": self.redirect_url,
                "methods": ["GET", "POST", "HEAD"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
            },
            {
                "path": "/user_storage_status",
                "endpoint": self._get_user_storage_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取115用户基本信息和空间状态",
            },
            {
                "path": "/get_config",
                "endpoint": self._get_config_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取配置",
            },
            {
                "path": "/save_config",
                "endpoint": self._save_config_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置",
            },
            {
                "path": "/get_status",
                "endpoint": self._get_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取状态",
            },
            {
                "path": "/full_sync",
                "endpoint": self._trigger_full_sync_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行全量同步",
            },
            {
                "path": "/share_sync",
                "endpoint": self._trigger_share_sync_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行分享同步",
            },
            {
                "path": "/browse_dir",
                "endpoint": self._browse_dir_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "浏览目录",
            },
            {
                "path": "/get_qrcode",
                "endpoint": self._get_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取登录二维码",
            },
            {
                "path": "/check_qrcode",
                "endpoint": self._check_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查二维码状态",
            },
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
        cron_service = []
        if (
            self._cron_full_sync_strm
            and self._timing_full_sync_strm
            and self._full_sync_strm_paths
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_full_sync_strm_files",
                    "name": "定期全量同步115媒体库",
                    "trigger": CronTrigger.from_crontab(self._cron_full_sync_strm),
                    "func": self.full_sync_strm_files,
                    "kwargs": {},
                }
            )
        if self._cron_clear and (
            self._clear_recyclebin_enabled or self._clear_receive_path_enabled
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_main_cleaner",
                    "name": "定期清理115空间",
                    "trigger": CronTrigger.from_crontab(self._cron_clear),
                    "func": self.main_cleaner,
                    "kwargs": {},
                }
            )
        if cron_service:
            return cron_service

    def __update_config(self):
        self.update_config(
            {
                "enabled": self._enabled,
                "notify": self._notify,
                "strm_url_format": self._strm_url_format,
                "cookies": self._cookies,
                "password": self._password,
                "moviepilot_address": self.moviepilot_address,
                "user_rmt_mediaext": self._user_rmt_mediaext,
                "user_download_mediaext": self._user_download_mediaext,
                "transfer_monitor_enabled": self._transfer_monitor_enabled,
                "transfer_monitor_scrape_metadata_enabled": self._transfer_monitor_scrape_metadata_enabled,
                "transfer_monitor_scrape_metadata_exclude_paths": self._transfer_monitor_scrape_metadata_exclude_paths,
                "transfer_monitor_paths": self._transfer_monitor_paths,
                "transfer_mp_mediaserver_paths": self._transfer_mp_mediaserver_paths,
                "transfer_monitor_media_server_refresh_enabled": self._transfer_monitor_media_server_refresh_enabled,
                "transfer_monitor_mediaservers": self._transfer_monitor_mediaservers,
                "timing_full_sync_strm": self._timing_full_sync_strm,
                "full_sync_auto_download_mediainfo_enabled": self._full_sync_auto_download_mediainfo_enabled,
                "cron_full_sync_strm": self._cron_full_sync_strm,
                "full_sync_strm_paths": self._full_sync_strm_paths,
                "monitor_life_enabled": self._monitor_life_enabled,
                "monitor_life_auto_download_mediainfo_enabled": self._monitor_life_auto_download_mediainfo_enabled,
                "monitor_life_paths": self._monitor_life_paths,
                "monitor_life_mp_mediaserver_paths": self._monitor_life_mp_mediaserver_paths,
                "monitor_life_media_server_refresh_enabled": self._monitor_life_media_server_refresh_enabled,
                "monitor_life_mediaservers": self._monitor_life_mediaservers,
                "monitor_life_auto_remove_local_enabled": self._monitor_life_auto_remove_local_enabled,
                "monitor_life_scrape_metadata_enabled": self._monitor_life_scrape_metadata_enabled,
                "monitor_life_scrape_metadata_exclude_paths": self._monitor_life_scrape_metadata_exclude_paths,
                "share_strm_auto_download_mediainfo_enabled": self._share_strm_auto_download_mediainfo_enabled,
                "user_share_code": self._user_share_code,
                "user_receive_code": self._user_receive_code,
                "user_share_link": self._user_share_link,
                "user_share_pan_path": self._user_share_pan_path,
                "user_share_local_path": self._user_share_local_path,
                "clear_recyclebin_enabled": self._clear_recyclebin_enabled,
                "clear_receive_path_enabled": self._clear_receive_path_enabled,
                "cron_clear": self._cron_clear,
                "pan_transfer_enabled": self._pan_transfer_enabled,
                "pan_transfer_paths": self._pan_transfer_paths,
            }
        )

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """
        返回插件使用的前端渲染模式
        :return: 前端渲染模式，前端文件目录
        """
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """
        为Vue组件模式返回初始配置数据。
        Vue模式下，第一个参数返回None，第二个参数返回初始配置数据。
        """
        return None, self._get_config_api()

    def get_page(self) -> Optional[List[dict]]:
        """
        Vue模式不使用Vuetify页面定义
        """
        return None

    def media_transfer(self, event, file_path: Path, rmt_mediaext):
        """
        运行媒体文件整理
        :param event: 事件
        :param file_path: 文件路径
        :param rmt_mediaext: 媒体文件后缀名
        """
        file_category = event["file_category"]
        file_id = event["file_id"]
        if file_category == 0:
            cache_top_path = False
            cache_file_id_list = []
            logger.info(f"【网盘整理】开始处理 {file_path} 文件夹中...")
            # 文件夹情况，遍历文件夹，获取整理文件
            # 缓存顶层文件夹ID
            if str(event["file_id"]) not in self.cache_delete_pan_transfer_list:
                self.cache_delete_pan_transfer_list.append(str(event["file_id"]))
            for item in iter_files_with_path(
                self._client, cid=int(file_id), cooldown=2
            ):
                file_path = Path(item["path"])
                # 缓存文件夹ID
                if str(item["parent_id"]) not in self.cache_delete_pan_transfer_list:
                    self.cache_delete_pan_transfer_list.append(str(item["parent_id"]))
                if file_path.suffix in rmt_mediaext:
                    # 缓存文件ID
                    if str(item["id"]) not in self.cache_creata_pan_transfer_list:
                        self.cache_creata_pan_transfer_list.append(str(item["id"]))
                    # 判断此顶层目录MP是否能处理
                    if str(item["parent_id"]) != event["file_id"]:
                        cache_top_path = True
                    if str(item["id"]) not in cache_file_id_list:
                        cache_file_id_list.append(str(item["id"]))
                    self.transferchain.do_transfer(
                        fileitem=FileItem(
                            storage="u115",
                            fileid=str(item["id"]),
                            parent_fileid=str(item["parent_id"]),
                            path=str(file_path).replace("\\", "/"),
                            type="file",
                            name=file_path.name,
                            basename=file_path.stem,
                            extension=file_path.suffix[1:],
                            size=item["size"],
                            pickcode=item["pickcode"],
                            modify_time=item["ctime"],
                        )
                    )
                    logger.info(f"【网盘整理】{file_path} 加入整理列队")

            # 顶层目录MP无法处理时添加到缓存字典中
            if cache_top_path and cache_file_id_list:
                if str(event["file_id"]) in self.cache_top_delete_pan_transfer_list:
                    # 如果存在相同ID的根目录则合并
                    cache_file_id_list = list(
                        dict.fromkeys(
                            chain(
                                cache_file_id_list,
                                self.cache_top_delete_pan_transfer_list[
                                    str(event["file_id"])
                                ],
                            )
                        )
                    )
                    del self.cache_top_delete_pan_transfer_list[str(event["file_id"])]
                self.cache_top_delete_pan_transfer_list[str(event["file_id"])] = (
                    cache_file_id_list
                )
        else:
            # 文件情况，直接整理
            if file_path.suffix in rmt_mediaext:
                # 缓存文件ID
                if str(event["file_id"]) not in self.cache_creata_pan_transfer_list:
                    self.cache_creata_pan_transfer_list.append(str(event["file_id"]))
                self.transferchain.do_transfer(
                    fileitem=FileItem(
                        storage="u115",
                        fileid=str(file_id),
                        parent_fileid=str(event["parent_id"]),
                        path=str(file_path).replace("\\", "/"),
                        type="file",
                        name=file_path.name,
                        basename=file_path.stem,
                        extension=file_path.suffix[1:],
                        size=event["file_size"],
                        pickcode=event["pick_code"],
                        modify_time=event["update_time"],
                    )
                )
                logger.info(f"【网盘整理】{file_path} 加入整理列队")

    def media_scrape_metadata(
        self,
        path,
        item_name: str = "",
        mediainfo: MediaInfo = None,
        meta: MetaBase = None,
    ):
        """
        媒体刮削服务
        :param path: 媒体文件路径
        :param item_name: 媒体名称
        :param meta: 元数据
        :param mediainfo: 媒体信息
        """
        item_name = item_name if item_name else Path(path).name
        logger.info(f"【媒体刮削】{item_name} 开始刮削元数据")
        if mediainfo:
            # 整理文件刮削
            if mediainfo.type == MediaType.MOVIE:
                # 电影刮削上级文件夹
                dir_path = Path(path).parent
                fileitem = FileItem(
                    storage="local",
                    type="dir",
                    path=str(dir_path),
                    name=dir_path.name,
                    basename=dir_path.stem,
                    modify_time=dir_path.stat().st_mtime,
                )
            else:
                # 电视剧刮削文件夹
                # 通过重命名格式判断根目录文件夹
                # 计算重命名中的文件夹层数
                rename_format_level = len(settings.TV_RENAME_FORMAT.split("/")) - 1
                if rename_format_level < 1:
                    file_path = Path(path)
                    fileitem = FileItem(
                        storage="local",
                        type="file",
                        path=str(file_path).replace("\\", "/"),
                        name=file_path.name,
                        basename=file_path.stem,
                        extension=file_path.suffix[1:],
                        size=file_path.stat().st_size,
                        modify_time=file_path.stat().st_mtime,
                    )
                else:
                    dir_path = Path(Path(path).parents[rename_format_level - 1])
                    fileitem = FileItem(
                        storage="local",
                        type="dir",
                        path=str(dir_path),
                        name=dir_path.name,
                        basename=dir_path.stem,
                        modify_time=dir_path.stat().st_mtime,
                    )
            self.mediachain.scrape_metadata(
                fileitem=fileitem, meta=meta, mediainfo=mediainfo
            )
        else:
            # 对于没有 mediainfo 的媒体文件刮削
            # 获取媒体信息
            meta = MetaInfoPath(Path(path))
            mediainfo = self.mediachain.recognize_by_meta(meta)
            # 判断刮削路径
            # 先获取上级目录 meta
            file_type = "dir"
            dir_path = Path(path).parent
            tem_mediainfo = self.mediachain.recognize_by_meta(MetaInfoPath(dir_path))
            # 只有上级目录信息和文件的信息一致时才继续判断上级目录
            if tem_mediainfo and tem_mediainfo.imdb_id == mediainfo.imdb_id:
                if mediainfo.type == MediaType.TV:
                    # 如果是电视剧，再次获取上级目录媒体信息，兼容电视剧命名，获取 mediainfo
                    dir_path = dir_path.parent
                    tem_mediainfo = self.mediachain.recognize_by_meta(
                        MetaInfoPath(dir_path)
                    )
                    if tem_mediainfo and tem_mediainfo.imdb_id == mediainfo.imdb_id:
                        # 存在 mediainfo 则使用本级目录
                        finish_path = dir_path
                    else:
                        # 否则使用上级目录
                        logger.warn(f"【媒体刮削】{dir_path} 无法识别文件媒体信息！")
                        finish_path = Path(path).parent
                else:
                    # 电影情况，使用当前目录和元数据
                    finish_path = dir_path
            else:
                # 如果上级目录没有媒体信息则使用传入的路径
                logger.warn(f"【媒体刮削】{dir_path} 无法识别文件媒体信息！")
                finish_path = Path(path)
                file_type = "file"
            fileitem = FileItem(
                storage="local",
                type=file_type,
                path=str(finish_path),
                name=finish_path.name,
                basename=finish_path.stem,
                modify_time=finish_path.stat().st_mtime,
            )
            self.mediachain.scrape_metadata(
                fileitem=fileitem, meta=meta, mediainfo=mediainfo
            )

        logger.info(f"【媒体刮削】{item_name} 刮削元数据完成")

    @cached(cache=TTLCache(maxsize=48, ttl=2 * 60))
    def redirect_url(
        self,
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
        app: str = "",
    ):
        """
        115网盘302跳转
        """

        def get_first(m: Mapping, *keys, default=None):
            for k in keys:
                if k in m:
                    return m[k]
            return default

        def share_get_id_for_name(
            share_code: str,
            receive_code: str,
            name: str,
            parent_id: int = 0,
        ) -> int:
            api = "http://web.api.115.com/share/search"
            payload = {
                "share_code": share_code,
                "receive_code": receive_code,
                "search_value": name,
                "cid": parent_id,
                "limit": 1,
                "type": 99,
            }
            suffix = name.rpartition(".")[-1]
            if suffix.isalnum():
                payload["suffix"] = suffix
            resp = requests.get(
                f"{api}?{urlencode(payload)}", headers={"Cookie": self._cookies}
            )
            check_response(resp)
            json = loads(cast(bytes, resp.content))
            if get_first(json, "errno", "errNo") == 20021:
                payload.pop("suffix")
                resp = requests.get(
                    f"{api}?{urlencode(payload)}", headers={"Cookie": self._cookies}
                )
                check_response(resp)
                json = loads(cast(bytes, resp.content))
            if not json["state"] or not json["data"]["count"]:
                raise FileNotFoundError(ENOENT, json)
            info = json["data"]["list"][0]
            if info["n"] != name:
                raise FileNotFoundError(ENOENT, f"name not found: {name!r}")
            id = int(info["fid"])
            return id

        def get_receive_code(share_code: str) -> str:
            resp = requests.get(
                f"http://web.api.115.com/share/shareinfo?share_code={share_code}",
                headers={"Cookie": self._cookies},
            )
            check_response(resp)
            json = loads(cast(bytes, resp.content))
            if not json["state"]:
                raise FileNotFoundError(ENOENT, json)
            receive_code = json["data"]["receive_code"]
            return receive_code

        def get_downurl(
            pickcode: str,
            user_agent: str = "",
            app: str = "android",
        ) -> Url:
            """
            获取下载链接
            """
            if app == "chrome":
                resp = requests.post(
                    "http://proapi.115.com/app/chrome/downurl",
                    data={
                        "data": encrypt(f'{{"pickcode":"{pickcode}"}}').decode("utf-8")
                    },
                    headers={"User-Agent": user_agent, "Cookie": self._cookies},
                )
            else:
                resp = requests.post(
                    f"http://proapi.115.com/{app or 'android'}/2.0/ufile/download",
                    data={
                        "data": encrypt(f'{{"pick_code":"{pickcode}"}}').decode("utf-8")
                    },
                    headers={"User-Agent": user_agent, "Cookie": self._cookies},
                )
            check_response(resp)
            json = loads(cast(bytes, resp.content))
            if not json["state"]:
                raise OSError(EIO, json)
            data = json["data"] = loads(decrypt(json["data"]))
            if app == "chrome":
                info = next(iter(data.values()))
                url_info = info["url"]
                if not url_info:
                    raise FileNotFoundError(ENOENT, dumps(json).decode("utf-8"))
                url = Url.of(url_info["url"], info)
            else:
                data["file_name"] = unquote(
                    urlsplit(data["url"]).path.rpartition("/")[-1]
                )
                url = Url.of(data["url"], data)
            return url

        def get_share_downurl(
            share_code: str,
            receive_code: str,
            file_id: int,
            app: str = "",
        ) -> Url:
            payload = {
                "share_code": share_code,
                "receive_code": receive_code,
                "file_id": file_id,
            }
            if app:
                resp = requests.get(
                    f"http://proapi.115.com/{app}/2.0/share/downurl?{urlencode(payload)}",
                    headers={"Cookie": self._cookies},
                )
            else:
                resp = requests.post(
                    "http://proapi.115.com/app/share/downurl",
                    data={"data": encrypt(dumps(payload)).decode("utf-8")},
                    headers={"Cookie": self._cookies},
                )
            check_response(resp)
            json = loads(cast(bytes, resp.content))
            if not json["state"]:
                if json.get("errno") == 4100008:
                    receive_code = get_receive_code(share_code)
                    return get_share_downurl(share_code, receive_code, file_id, app=app)
                raise OSError(EIO, json)
            if app:
                data = json["data"]
            else:
                data = json["data"] = loads(decrypt(json["data"]))
            if not (data and (url_info := data["url"])):
                raise FileNotFoundError(ENOENT, json)
            data["file_id"] = data.pop("fid")
            data["file_name"] = data.pop("fn")
            data["file_size"] = int(data.pop("fs"))
            url = Url.of(url_info["url"], data)
            return url

        if share_code:
            try:
                if not receive_code:
                    receive_code = get_receive_code(share_code)
                elif len(receive_code) != 4:
                    return f"Bad receive_code: {receive_code}"
                if not id:
                    if file_name:
                        id = share_get_id_for_name(
                            share_code,
                            receive_code,
                            file_name,
                        )
                if not id:
                    return f"Please specify id or name: share_code={share_code!r}"
                url = get_share_downurl(share_code, receive_code, id, app=app)
                logger.info(f"【302跳转服务】获取 115 下载地址成功: {url}")
            except Exception as e:
                logger.error(f"【302跳转服务】获取 115 下载地址失败: {e}")
                return f"获取 115 下载地址失败: {e}"
        else:
            if not pickcode:
                logger.debug("【302跳转服务】Missing pickcode parameter")
                return "Missing pickcode parameter"

            if not (len(pickcode) == 17 and pickcode.isalnum()):
                logger.debug(f"【302跳转服务】Bad pickcode: {pickcode} {file_name}")
                return f"Bad pickcode: {pickcode} {file_name}"

            user_agent = request.headers.get("User-Agent") or b""
            logger.debug(f"【302跳转服务】获取到客户端UA: {user_agent}")

            try:
                url = get_downurl(pickcode.lower(), user_agent, app=app)
                logger.info(f"【302跳转服务】获取 115 下载地址成功: {url}")
            except Exception as e:
                logger.error(f"【302跳转服务】获取 115 下载地址失败: {e}")
                return f"获取 115 下载地址失败: {e}"

        return Response(
            status_code=302,
            headers={
                "Location": url,
                "Content-Disposition": f'attachment; filename="{quote(url["file_name"])}"',
            },
            media_type="application/json; charset=utf-8",
            content=dumps({"status": "redirecting", "url": url}),
        )

    @eventmanager.register(EventType.TransferComplete)
    def delete_top_pan_transfer_path(self, event: Event):
        """
        处理网盘整理MP无法删除的顶层目录
        """

        if not self._pan_transfer_enabled or not self._pan_transfer_paths:
            return

        if not self.cache_top_delete_pan_transfer_list:
            return

        item = event.event_data
        if not item:
            return

        item_transfer: TransferInfo = item.get("transferinfo")
        dest_fileitem: FileItem = item_transfer.target_item
        src_fileitem: FileItem = item.get("fileitem")

        if item_transfer.transfer_type != "move":
            return

        if dest_fileitem.storage != "u115" or src_fileitem.storage != "u115":
            return

        if not self.pathmatchinghelper.get_run_transfer_path(
            paths=self._pan_transfer_paths, transfer_path=src_fileitem.path
        ):
            return

        remove_id = ""
        for key, item_list in self.cache_top_delete_pan_transfer_list.items():
            self.cache_top_delete_pan_transfer_list[key] = [
                item for item in item_list if item != str(dest_fileitem.fileid)
            ]
            remove_id = key
            break

        if remove_id:
            if not self.cache_top_delete_pan_transfer_list.get(remove_id):
                del self.cache_top_delete_pan_transfer_list[remove_id]
                resp = self._client.fs_delete(int(remove_id))
                if resp["state"]:
                    logger.info(f"【网盘整理】删除 {remove_id} 文件夹成功")
                else:
                    logger.error(f"【网盘整理】删除 {remove_id} 文件夹失败: {resp}")

        return

    @eventmanager.register(EventType.TransferComplete)
    def generate_strm(self, event: Event):
        """
        监控目录整理生成 STRM 文件
        """

        def generate_strm_files(
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
                if self.pathmatchinghelper.has_prefix(pan_path, pan_media_dir):
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

        if (
            not self._enabled
            or not self._transfer_monitor_enabled
            or not self._transfer_monitor_paths
            or not self.moviepilot_address
        ):
            return

        item = event.event_data
        if not item:
            return

        # 转移信息
        item_transfer: TransferInfo = item.get("transferinfo")
        # 媒体信息
        mediainfo: MediaInfo = item.get("mediainfo")
        # 元数据信息
        meta: MetaBase = item.get("meta")

        item_dest_storage: FileItem = item_transfer.target_item.storage
        if item_dest_storage != "u115":
            return

        # 网盘目的地目录
        itemdir_dest_path: FileItem = item_transfer.target_diritem.path
        # 网盘目的地路径（包含文件名称）
        item_dest_path: FileItem = item_transfer.target_item.path
        # 网盘目的地文件名称
        item_dest_name: FileItem = item_transfer.target_item.name
        # 网盘目的地文件名称（不包含后缀）
        item_dest_basename: FileItem = item_transfer.target_item.basename
        # 网盘目的地文件 pickcode
        item_dest_pickcode: FileItem = item_transfer.target_item.pickcode
        # 是否蓝光原盘
        item_bluray = SystemUtils.is_bluray_dir(Path(itemdir_dest_path))

        __itemdir_dest_path, local_media_dir, pan_media_dir = (
            self.pathmatchinghelper.get_media_path(
                self._transfer_monitor_paths, itemdir_dest_path
            )
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
        strm_url = f"{self.moviepilot_address.rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={item_dest_pickcode}"
        if self._strm_url_format == "pickname":
            strm_url += f"&file_name={item_dest_name}"

        status, strm_target_path = generate_strm_files(
            target_dir=local_media_dir,
            pan_media_dir=pan_media_dir,
            item_dest_path=item_dest_path,
            basename=item_dest_basename,
            url=strm_url,
        )
        if not status:
            return

        scrape_metadata = True
        if self._transfer_monitor_scrape_metadata_enabled:
            if self._transfer_monitor_scrape_metadata_exclude_paths:
                if self.pathmatchinghelper.get_scrape_metadata_exclude_path(
                    self._transfer_monitor_scrape_metadata_exclude_paths,
                    str(strm_target_path),
                ):
                    logger.debug(
                        f"【监控整理STRM生成】匹配到刮削排除目录，不进行刮削: {strm_target_path}"
                    )
                    scrape_metadata = False
            if scrape_metadata:
                self.media_scrape_metadata(
                    path=strm_target_path,
                    item_name=item_dest_name,
                    mediainfo=mediainfo,
                    meta=meta,
                )

        if self._transfer_monitor_media_server_refresh_enabled:
            if not self.transfer_service_infos:
                return

            logger.info(f"【监控整理STRM生成】 {item_dest_name} 开始刷新媒体服务器")

            if self._transfer_mp_mediaserver_paths:
                status, mediaserver_path, moviepilot_path = (
                    self.pathmatchinghelper.get_media_path(
                        self._transfer_mp_mediaserver_paths, strm_target_path
                    )
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

    @eventmanager.register(EventType.PluginAction)
    def p115_full_sync(self, event: Event):
        """
        远程全量同步
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_full_sync":
            return
        self.post_message(
            channel=event.event_data.get("channel"),
            title="开始115网盘媒体库全量同步 ...",
            userid=event.event_data.get("user"),
        )
        self.full_sync_strm_files()

    def add_share(self, url, channel, userid):
        """
        分享转存
        """
        if not self._pan_transfer_enabled or not self._pan_transfer_paths:
            self.post_message(
                channel=channel,
                title="配置错误！ 请先进入插件界面配置网盘整理",
                userid=userid,
            )
            return
        try:
            data = share_extract_payload(url)
            share_code = data["share_code"]
            receive_code = data["receive_code"]
            logger.info(
                f"【分享转存】解析分享链接 share_code={share_code} receive_code={receive_code}"
            )
            if not share_code or not receive_code:
                logger.error(f"【分享转存】解析分享链接失败：{url}")
                self.post_message(
                    channel=channel,
                    title=f"解析分享链接失败：{url}",
                    userid=userid,
                )
                return
            parent_path = self._pan_transfer_paths.split("\n")[0]
            parent_id = self.id_path_cache.get_id_by_dir(directory=str(parent_path))
            if not parent_id:
                parent_id = self._client.fs_dir_getid(parent_path)["id"]
                logger.info(f"【分享转存】获取到转存目录 ID：{parent_id}")
                self.id_path_cache.add_cache(
                    id=int(parent_id), directory=str(parent_path)
                )
            payload = {
                "share_code": share_code,
                "receive_code": receive_code,
                "file_id": 0,
                "cid": int(parent_id),
                "is_check": 0,
            }
            logger.info(f"【分享转存】开始转存：{share_code}")
            self.post_message(
                channel=channel,
                title=f"开始转存：{share_code}",
                userid=userid,
            )
            resp = self._client.share_receive(payload)
            if resp["state"]:
                logger.info(f"【分享转存】转存 {share_code} 到 {parent_path} 成功！")
                self.post_message(
                    channel=channel,
                    title=f"转存 {share_code} 到 {parent_path} 成功！",
                    userid=userid,
                )
            else:
                logger.info(f"【分享转存】转存 {share_code} 失败：{resp['error']}")
                self.post_message(
                    channel=channel,
                    title=f"转存 {share_code} 失败：{resp['error']}",
                    userid=userid,
                )
            return
        except Exception as e:
            logger.error(f"【分享转存】运行失败: {e}")
            return

    @eventmanager.register(EventType.UserMessage)
    def user_add_share(self, event: Event):
        """
        远程分享转存
        """
        if not self._enabled:
            return
        text = event.event_data.get("text")
        userid = event.event_data.get("userid")
        channel = event.event_data.get("channel")
        if not text:
            return
        if not text.startswith("http"):
            return
        if not bool(re.match(r"^https?://(.*\.)?115[^/]*\.[a-zA-Z]{2,}(?:\/|$)", text)):
            return
        self.add_share(
            url=text,
            channel=channel,
            userid=userid,
        )
        return

    @eventmanager.register(EventType.PluginAction)
    def p115_add_share(self, event: Event):
        """
        远程分享转存
        """
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "p115_add_share":
                return
            args = event_data.get("arg_str")
            if not args:
                logger.error(f"【分享转存】缺少参数：{event_data}")
                self.post_message(
                    channel=event.event_data.get("channel"),
                    title="参数错误！ /p115_add_share 分享链接",
                    userid=event.event_data.get("user"),
                )
                return
        self.add_share(
            url=args,
            channel=event.event_data.get("channel"),
            userid=event.event_data.get("user"),
        )
        return

    def full_sync_strm_files(self):
        """
        全量同步
        """
        if (
            not self._full_sync_strm_paths
            or not self.moviepilot_address
            or not self._user_download_mediaext
        ):
            return

        strm_helper = FullSyncStrmHelper(
            user_rmt_mediaext=self._user_rmt_mediaext,
            user_download_mediaext=self._user_download_mediaext,
            auto_download_mediainfo=self._full_sync_auto_download_mediainfo_enabled,
            client=self._client,
            mediainfodownloader=self.mediainfodownloader,
            server_address=self.moviepilot_address,
            pan_transfer_enabled=self._pan_transfer_enabled,
            pan_transfer_paths=self._pan_transfer_paths,
            strm_url_format=self._strm_url_format,
        )
        strm_helper.generate_strm_files(
            full_sync_strm_paths=self._full_sync_strm_paths,
        )
        strm_count, mediainfo_count, strm_fail_count, mediainfo_fail_count = (
            strm_helper.get_generate_total()
        )
        if self._notify:
            self.post_message(
                mtype=NotificationType.Plugin,
                title="✅【115网盘】全量生成 STRM 文件完成",
                text=f"📂 生成STRM文件 {strm_count} 个\n"
                + f"⬇️ 下载媒体文件 {mediainfo_count} 个\n"
                + f"❌ 生成STRM失败 {strm_fail_count} 个\n"
                + f"🚫 下载媒体失败 {mediainfo_fail_count} 个",
            )

    def share_strm_files(self):
        """
        分享生成STRM
        """
        if (
            not self._user_share_pan_path
            or not self._user_share_local_path
            or not self.moviepilot_address
        ):
            return

        if self._user_share_link:
            data = share_extract_payload(self._user_share_link)
            share_code = data["share_code"]
            receive_code = data["receive_code"]
            logger.info(
                f"【分享STRM生成】解析分享链接 share_code={share_code} receive_code={receive_code}"
            )
        else:
            if not self._user_share_code or not self._user_receive_code:
                return
            share_code = self._user_share_code
            receive_code = self._user_receive_code

        try:
            strm_helper = ShareStrmHelper(
                user_rmt_mediaext=self._user_rmt_mediaext,
                user_download_mediaext=self._user_download_mediaext,
                auto_download_mediainfo=self._share_strm_auto_download_mediainfo_enabled,
                client=self._client,
                server_address=self.moviepilot_address,
                share_media_path=self._user_share_pan_path,
                local_media_path=self._user_share_local_path,
                mediainfodownloader=self.mediainfodownloader,
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
            if self._notify:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title="✅【115网盘】分享生成 STRM 文件完成",
                    text=f"📂 生成STRM文件 {strm_count} 个\n"
                    + f"⬇️ 下载媒体文件 {mediainfo_count} 个\n"
                    + f"❌ 生成STRM失败 {strm_fail_count} 个\n"
                    + f"🚫 下载媒体失败 {mediainfo_fail_count} 个",
                )
        except Exception as e:
            logger.error(f"【分享STRM生成】运行失败: {e}")
            return

    def monitor_life_strm_files(self):
        """
        监控115生活事件

        {
            1: "upload_image_file",  上传图片 生成 STRM
            2: "upload_file",        上传文件/目录 生成 STRM
            3: "star_image",         标星图片 无操作
            4: "star_file",          标星文件/目录 无操作
            5: "move_image_file",    移动图片 生成 STRM
            6: "move_file",          移动文件/目录 生成 STRM
            7: "browse_image",       浏览图片 无操作
            8: "browse_video",       浏览视频 无操作
            9: "browse_audio",       浏览音频 无操作
            10: "browse_document",   浏览文档 无操作
            14: "receive_files",     接收文件 生成 STRM
            17: "new_folder",        创建新目录 无操作
            18: "copy_folder",       复制文件夹 生成 STRM
            19: "folder_label",      标签文件夹 无操作
            20: "folder_rename",     重命名文件夹 无操作
            22: "delete_file",       删除文件/文件夹 删除 STRM
        }

        注意: 目前没有重命名文件，复制文件的操作事件
        """

        def _schedule_notification():
            """
            安排通知发送，如果一分钟内没有新事件则发送
            """
            if self._monitor_life_notification_timer:
                self._monitor_life_notification_timer.cancel()

            self._monitor_life_notification_timer = Timer(60.0, _send_notification)
            self._monitor_life_notification_timer.start()

        def _send_notification():
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
                text_parts.append(f"📂 生成STRM文件 {counts['strm_count']} 个")
            if counts["mediainfo_count"] > 0:
                text_parts.append(f"⬇️ 下载媒体文件 {counts['mediainfo_count']} 个")

            if text_parts and self._notify:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title="✅【115网盘】生活事件生成 STRM 文件",
                    text="\n".join(text_parts),
                )

            # 重置计数器
            self._monitor_life_notification_queue["life"] = {
                "strm_count": 0,
                "mediainfo_count": 0,
            }

        def refresh_mediaserver(file_path: str, file_name: str):
            """
            刷新媒体服务器
            """
            if self._monitor_life_media_server_refresh_enabled:
                if not self.monitor_life_service_infos:
                    return
                logger.info(f"【监控生活事件】 {file_name} 开始刷新媒体服务器")
                if self._monitor_life_mp_mediaserver_paths:
                    status, mediaserver_path, moviepilot_path = (
                        self.pathmatchinghelper.get_media_path(
                            self._monitor_life_mp_mediaserver_paths, file_path
                        )
                    )
                    if status:
                        logger.info(
                            f"【监控生活事件】 {file_name} 刷新媒体服务器目录替换中..."
                        )
                        file_path = file_path.replace(
                            moviepilot_path, mediaserver_path
                        ).replace("\\", "/")
                        logger.info(
                            f"【监控生活事件】刷新媒体服务器目录替换: {moviepilot_path} --> {mediaserver_path}"
                        )
                        logger.info(f"【监控生活事件】刷新媒体服务器目录: {file_path}")
                items = [
                    RefreshMediaItem(
                        title=None,
                        year=None,
                        type=None,
                        category=None,
                        target_path=Path(file_path),
                    )
                ]
                for name, service in self.monitor_life_service_infos.items():
                    if hasattr(service.instance, "refresh_library_by_items"):
                        service.instance.refresh_library_by_items(items)
                    elif hasattr(service.instance, "refresh_root_library"):
                        service.instance.refresh_root_library()
                    else:
                        logger.warning(f"【监控生活事件】{file_name} {name} 不支持刷新")

        def creata_strm(event, file_path):
            """
            创建 STRM 文件
            """
            _databasehelper = FileDbHelper()

            pickcode = event["pick_code"]
            file_category = event["file_category"]
            file_id = event["file_id"]
            status, target_dir, pan_media_dir = self.pathmatchinghelper.get_media_path(
                self._monitor_life_paths, file_path
            )
            if not status:
                return
            logger.debug("【监控生活事件】匹配到网盘文件夹路径: %s", str(pan_media_dir))

            if file_category == 0:
                # 文件夹情况，遍历文件夹
                mediainfo_count = 0
                strm_count = 0
                for batch in batched(
                    iter_files_with_path(self._client, cid=int(file_id), cooldown=2),
                    7_000,
                ):
                    processed = []
                    for item in batch:
                        _process_item = _databasehelper.process_item(item)
                        if _process_item not in processed:
                            processed.extend(_process_item)
                        if item["is_dir"] or item["is_directory"]:
                            continue
                        file_path = item["path"]
                        file_path = Path(target_dir) / Path(file_path).relative_to(
                            pan_media_dir
                        )
                        file_target_dir = file_path.parent
                        original_file_name = file_path.name
                        file_name = file_path.stem + ".strm"
                        new_file_path = file_target_dir / file_name

                        if self._monitor_life_auto_download_mediainfo_enabled:
                            if file_path.suffix in download_mediaext:
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

                        if file_path.suffix not in rmt_mediaext:
                            logger.warn(
                                "【监控生活事件】跳过网盘路径: %s",
                                str(file_path).replace(str(target_dir), "", 1),
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
                        strm_url = f"{self.moviepilot_address.rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={pickcode}"
                        if self._strm_url_format == "pickname":
                            strm_url += f"&file_name={original_file_name}"

                        with open(new_file_path, "w", encoding="utf-8") as file:
                            file.write(strm_url)
                        logger.info(
                            "【监控生活事件】生成 STRM 文件成功: %s", str(new_file_path)
                        )
                        strm_count += 1
                        scrape_metadata = True
                        if self._monitor_life_scrape_metadata_enabled:
                            if self._monitor_life_scrape_metadata_exclude_paths:
                                if self.pathmatchinghelper.get_scrape_metadata_exclude_path(
                                    self._monitor_life_scrape_metadata_exclude_paths,
                                    str(new_file_path),
                                ):
                                    logger.debug(
                                        f"【监控生活事件】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                                    )
                                    scrape_metadata = False
                            if scrape_metadata:
                                self.media_scrape_metadata(
                                    path=new_file_path,
                                )
                        # 刷新媒体服务器
                        refresh_mediaserver(str(new_file_path), str(original_file_name))
                    _databasehelper.upsert_batch(processed)
                if self._notify:
                    if strm_count > 0 or mediainfo_count > 0:
                        self._monitor_life_notification_queue["life"]["strm_count"] += (
                            strm_count
                        )
                        self._monitor_life_notification_queue["life"][
                            "mediainfo_count"
                        ] += mediainfo_count
                        _schedule_notification()
            else:
                _databasehelper.upsert_batch(
                    [
                        {
                            "table": "files",
                            "data": {
                                "id": event["file_id"],
                                "parent_id": event["parent_id"],
                                "name": event["file_name"],
                                "sha1": event.get("sha1", ""),
                                "size": event.get("file_size", 0),
                                "pickcode": event.get("pick_code", ""),
                                "ctime": event.get("create_time", 0),
                                "mtime": event.get("update_time", 0),
                                "path": str(file_path),
                                "extra": str(event),
                            },
                        }
                    ]
                )
                # 文件情况，直接生成
                file_path = Path(target_dir) / Path(file_path).relative_to(
                    pan_media_dir
                )
                file_target_dir = file_path.parent
                original_file_name = file_path.name
                file_name = file_path.stem + ".strm"
                new_file_path = file_target_dir / file_name

                if self._monitor_life_auto_download_mediainfo_enabled:
                    if file_path.suffix in download_mediaext:
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
                        if self._notify:
                            self._monitor_life_notification_queue["life"][
                                "mediainfo_count"
                            ] += 1
                            _schedule_notification()
                        return

                if file_path.suffix not in rmt_mediaext:
                    logger.warn(
                        "【监控生活事件】跳过网盘路径: %s",
                        str(file_path).replace(str(target_dir), "", 1),
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
                strm_url = f"{self.moviepilot_address.rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={pickcode}"
                if self._strm_url_format == "pickname":
                    strm_url += f"&file_name={original_file_name}"

                with open(new_file_path, "w", encoding="utf-8") as file:
                    file.write(strm_url)
                logger.info(
                    "【监控生活事件】生成 STRM 文件成功: %s", str(new_file_path)
                )
                if self._notify:
                    self._monitor_life_notification_queue["life"]["strm_count"] += 1
                    _schedule_notification()
                scrape_metadata = True
                if self._monitor_life_scrape_metadata_enabled:
                    if self._monitor_life_scrape_metadata_exclude_paths:
                        if self.pathmatchinghelper.get_scrape_metadata_exclude_path(
                            self._monitor_life_scrape_metadata_exclude_paths,
                            str(new_file_path),
                        ):
                            logger.debug(
                                f"【监控生活事件】匹配到刮削排除目录，不进行刮削: {new_file_path}"
                            )
                            scrape_metadata = False
                    if scrape_metadata:
                        self.media_scrape_metadata(
                            path=new_file_path,
                        )
                # 刷新媒体服务器
                refresh_mediaserver(str(new_file_path), str(original_file_name))

        def remove_strm(event):
            """
            删除 STRM 文件
            """

            def __remove_parent_dir(file_path: Path):
                """
                删除父目录
                """
                # 删除空目录
                # 判断当前媒体父路径下是否有媒体文件，如有则无需遍历父级
                if not SystemUtils.exits_files(file_path.parent, ["strm"]):
                    # 判断父目录是否为空, 为空则删除
                    i = 0
                    for parent_path in file_path.parents:
                        i += 1
                        if i > 3:
                            break
                        if str(parent_path.parent) != str(file_path.root):
                            # 父目录非根目录，才删除父目录
                            if not SystemUtils.exits_files(parent_path, ["strm"]):
                                # 当前路径下没有媒体文件则删除
                                shutil.rmtree(parent_path)
                                logger.warn(
                                    f"【监控生活事件】本地空目录 {parent_path} 已删除"
                                )

            def __get_file_path(
                file_name: str, file_size: str, file_id: str, file_category: int
            ):
                """
                通过 还原文件/文件夹 再删除 获取文件路径
                """
                for item in self._client.recyclebin_list()["data"]:
                    if (
                        file_category == 0
                        and str(item["file_name"]) == file_name
                        and str(item["type"]) == "2"
                    ) or (
                        file_category != 0
                        and str(item["file_name"]) == file_name
                        and str(item["file_size"]) == file_size
                    ):
                        resp = self._client.recyclebin_revert(item["id"])
                        if resp["state"]:
                            time.sleep(1)
                            path = get_path_to_cid(self._client, cid=int(item["cid"]))
                            time.sleep(1)
                            self._client.fs_delete(file_id)
                            return str(Path(path) / item["file_name"])
                        else:
                            return None
                return None

            _databasehelper = FileDbHelper()

            file_path = None
            file_category = event["file_category"]
            file_item = _databasehelper.get_by_id(int(event["file_id"]))
            if file_item:
                file_path = file_item.get("path", "")
            if not file_path:
                file_path = __get_file_path(
                    file_name=str(event["file_name"]),
                    file_size=str(event["file_size"]),
                    file_id=str(event["file_id"]),
                    file_category=file_category,
                )
            else:
                logger.debug(f"【监控生活事件】通过数据库获取路径：{file_path}")
            if not file_path:
                return

            pan_file_path = file_path
            # 优先匹配待整理目录，如果删除的目录为待整理目录则不进行操作
            if self._pan_transfer_enabled and self._pan_transfer_paths:
                if self.pathmatchinghelper.get_run_transfer_path(
                    paths=self._pan_transfer_paths, transfer_path=file_path
                ):
                    logger.debug(
                        f"【监控生活事件】{file_path} 为待整理目录下的路径，不做处理"
                    )
                    return

            # 匹配是否是媒体文件夹目录
            status, target_dir, pan_media_dir = self.pathmatchinghelper.get_media_path(
                self._monitor_life_paths, file_path
            )
            if not status:
                return
            logger.debug("【监控生活事件】匹配到网盘文件夹路径: %s", str(pan_media_dir))

            file_path = Path(target_dir) / Path(file_path).relative_to(pan_media_dir)
            if file_path.suffix in rmt_mediaext:
                file_target_dir = file_path.parent
                file_name = file_path.stem + ".strm"
                file_path = file_target_dir / file_name
            logger.info(
                f"【监控生活事件】删除本地{'文件夹' if file_category == 0 else '文件'}: {file_path}"
            )
            if file_category == 0:
                shutil.rmtree(Path(file_path))
            else:
                Path(file_path).unlink(missing_ok=True)
                __remove_parent_dir(Path(file_path))
            logger.info(pan_file_path)
            _databasehelper.remove_by_path_batch(str(pan_file_path))
            logger.info(f"【监控生活事件】{file_path} 已删除")

        def new_creata_path(event):
            """
            处理新出现的路径
            """
            # 1.获取绝对文件路径
            file_name = event["file_name"]
            dir_path = self.id_path_cache.get_dir_by_id(int(event["parent_id"]))
            if not dir_path:
                dir_path = get_path_to_cid(self._client, cid=int(event["parent_id"]))
                logger.debug(
                    f"【监控生活事件】获取 {event['parent_id']} 路径: {dir_path}"
                )
                self.id_path_cache.add_cache(
                    id=int(event["parent_id"]), directory=str(dir_path)
                )
            file_path = Path(dir_path) / file_name
            # 匹配逻辑 整理路径目录 > 生成STRM文件路径目录
            # 2.匹配是否为整理路径目录
            if self._pan_transfer_enabled and self._pan_transfer_paths:
                if self.pathmatchinghelper.get_run_transfer_path(
                    paths=self._pan_transfer_paths, transfer_path=file_path
                ):
                    self.media_transfer(
                        event=event,
                        file_path=Path(file_path),
                        rmt_mediaext=rmt_mediaext,
                    )
                    return
            # 3.匹配是否为生成STRM文件路径目录
            if self._monitor_life_enabled and self._monitor_life_paths:
                if str(event["file_id"]) in self.cache_creata_pan_transfer_list:
                    # 检查是否命中缓存，命中则不处理
                    self.cache_creata_pan_transfer_list.remove(str(event["file_id"]))
                else:
                    creata_strm(event=event, file_path=file_path)

        resp = life_show(self._client)
        if not resp["state"]:
            logger.error(f"【监控生活事件】生活事件开启失败: {resp}")
            return
        logger.info("【监控生活事件】生活事件监控启动中...")
        try:
            # 删除缓存，避免删除无限循环
            delete_list = []
            for events_batch in iter_life_behavior_list(self._client, cooldown=int(20)):
                if self.monitor_stop_event.is_set():
                    logger.info("【监控生活事件】收到停止信号，退出上传事件监控")
                    break
                if not events_batch:
                    time.sleep(20)
                    continue
                for event in events_batch:
                    rmt_mediaext = [
                        f".{ext.strip()}"
                        for ext in self._user_rmt_mediaext.replace("，", ",").split(",")
                    ]
                    download_mediaext = [
                        f".{ext.strip()}"
                        for ext in self._user_download_mediaext.replace(
                            "，", ","
                        ).split(",")
                    ]
                    if (
                        int(event["type"]) != 1
                        and int(event["type"]) != 2
                        and int(event["type"]) != 5
                        and int(event["type"]) != 6
                        and int(event["type"]) != 14
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
                        new_creata_path(event=event)

                    if int(event["type"]) == 22:
                        # 删除文件/文件夹事件处理
                        if event["file_id"] in delete_list:
                            # 通过 delete_list 避免反复删除
                            delete_list.remove(event["file_id"])
                        elif (
                            str(event["file_id"]) in self.cache_delete_pan_transfer_list
                        ):
                            # 检查是否命中删除文件夹缓存，命中则无需处理
                            self.cache_delete_pan_transfer_list.remove(
                                str(event["file_id"])
                            )
                        else:
                            if (
                                self._monitor_life_enabled
                                and self._monitor_life_paths
                                and self._monitor_life_auto_remove_local_enabled
                            ):
                                delete_list.append(event["file_id"])
                                remove_strm(event=event)

        except Exception as e:
            logger.error(f"【监控生活事件】生活事件监控运行失败: {e}")
            logger.info("【监控生活事件】30s 后尝试重新启动生活事件监控")
            time.sleep(30)
            self.monitor_life_strm_files()
        logger.info("【监控生活事件】已退出生活事件监控")
        return

    def main_cleaner(self):
        """
        主清理模块
        """
        if self._clear_receive_path_enabled:
            self.clear_receive_path()

        if self._clear_recyclebin_enabled:
            self.clear_recyclebin()

    def clear_recyclebin(self):
        """
        清空回收站
        """
        try:
            logger.info("【回收站清理】开始清理回收站")
            self._client.recyclebin_clean(password=self._password)
            logger.info("【回收站清理】回收站已清空")
        except Exception as e:
            logger.error(f"【回收站清理】清理回收站运行失败: {e}")
            return

    def clear_receive_path(self):
        """
        清空我的接收
        """
        try:
            logger.info("【我的接收清理】开始清理我的接收")
            parent_id = int(self._client.fs_dir_getid("/我的接收")["id"])
            if parent_id == 0:
                logger.info("【我的接收清理】我的接收目录为空，无需清理")
                return
            logger.info(f"【我的接收清理】我的接收目录 ID 获取成功: {parent_id}")
            self._client.fs_delete(parent_id)
            logger.info("【我的接收清理】我的接收已清空")
        except Exception as e:
            logger.error(f"【我的接收清理】清理我的接收运行失败: {e}")
            return

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
            self.monitor_stop_event.set()
        except Exception as e:
            print(str(e))

    @cached(cache=TTLCache(maxsize=1, ttl=60 * 60))
    def _get_user_storage_status(self) -> Dict[str, Any]:
        """
        获取115用户基本信息和空间使用情况。
        """
        if not self._cookies:
            return {
                "success": False,
                "error_message": "115 Cookies 未配置，无法获取信息。",
                "user_info": None,
                "storage_info": None,
            }

        try:
            if not self._client:
                try:
                    _temp_client = P115Client(self._cookies)
                    logger.info("【用户存储状态】P115Client 初始化成功")
                except Exception as e:
                    logger.error(f"【用户存储状态】P115Client 初始化失败: {e}")
                    return {
                        "success": False,
                        "error_message": f"115客户端初始化失败: {e}",
                        "user_info": None,
                        "storage_info": None,
                    }
            else:
                _temp_client = self._client

            # 获取用户信息
            user_info_resp = _temp_client.user_my_info()
            user_details: Dict = None
            if user_info_resp.get("state"):
                data = user_info_resp.get("data", {})
                vip_data = data.get("vip", {})
                face_data = data.get("face", {})
                user_details = {
                    "name": data.get("uname"),
                    "is_vip": vip_data.get("is_vip"),
                    "is_forever_vip": vip_data.get("is_forever"),
                    "vip_expire_date": vip_data.get("expire_str")
                    if not vip_data.get("is_forever")
                    else "永久",
                    "avatar": face_data.get("face_s"),
                }
                logger.info(
                    f"【用户存储状态】获取用户信息成功: {user_details.get('name')}"
                )
            else:
                error_msg = (
                    user_info_resp.get("message", "获取用户信息失败")
                    if user_info_resp
                    else "获取用户信息响应为空"
                )
                logger.error(f"【用户存储状态】获取用户信息失败: {error_msg}")
                return {
                    "success": False,
                    "error_message": f"获取115用户信息失败: {error_msg}",
                    "user_info": None,
                    "storage_info": None,
                }

            # 获取空间信息
            space_info_resp = _temp_client.fs_index_info(payload=0)
            storage_details = None
            if space_info_resp.get("state"):
                data = space_info_resp.get("data", {}).get("space_info", {})
                storage_details = {
                    "total": data.get("all_total", {}).get("size_format"),
                    "used": data.get("all_use", {}).get("size_format"),
                    "remaining": data.get("all_remain", {}).get("size_format"),
                }
                logger.info(
                    f"【用户存储状态】获取空间信息成功: 总-{storage_details.get('total')}"
                )
            else:
                error_msg = (
                    space_info_resp.get("error", "获取空间信息失败")
                    if space_info_resp
                    else "获取空间信息响应为空"
                )
                logger.error(f"【用户存储状态】获取空间信息失败: {error_msg}")
                return {
                    "success": False,
                    "error_message": f"获取115空间信息失败: {error_msg}",
                    "user_info": user_details,
                    "storage_info": None,
                }

            return {
                "success": True,
                "user_info": user_details,
                "storage_info": storage_details,
            }

        except Exception as e:
            logger.error(f"【用户存储状态】获取信息时发生意外错误: {e}", exc_info=True)
            error_str_lower = str(e).lower()
            if (
                isinstance(e, DataError)
                and ("errno 61" in error_str_lower or "enodata" in error_str_lower)
                and "<!doctype html>" in error_str_lower
            ):
                specific_error_message = "获取115账户信息失败：Cookie无效或已过期，请在插件配置中重新扫码登录。"
            elif (
                "cookie" in error_str_lower
                or "登录" in error_str_lower
                or "登陆" in error_str_lower
            ):
                specific_error_message = (
                    f"获取115账户信息失败：{str(e)} 请检查Cookie或重新登录。"
                )
            else:
                specific_error_message = f"处理请求时发生错误: {str(e)}"

            result_to_return = {
                "success": False,
                "error_message": specific_error_message,
                "user_info": None,
                "storage_info": None,
            }
            return result_to_return

    def _get_config_api(self) -> Dict:
        """
        获取配置
        """
        return {
            "enabled": self._enabled,
            "notify": self._notify,
            "strm_url_format": self._strm_url_format or "pickcode",
            "cookies": self._cookies or "",
            "password": self._password or "",
            "moviepilot_address": self.moviepilot_address or "",
            "user_rmt_mediaext": self._user_rmt_mediaext
            or "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
            "user_download_mediaext": self._user_download_mediaext or "srt,ssa,ass",
            "transfer_monitor_enabled": self._transfer_monitor_enabled,
            "transfer_monitor_scrape_metadata_enabled": self._transfer_monitor_scrape_metadata_enabled,
            "transfer_monitor_scrape_metadata_exclude_paths": self._transfer_monitor_scrape_metadata_exclude_paths
            or "",
            "transfer_monitor_paths": self._transfer_monitor_paths or "",
            "transfer_mp_mediaserver_paths": self._transfer_mp_mediaserver_paths or "",
            "transfer_monitor_media_server_refresh_enabled": self._transfer_monitor_media_server_refresh_enabled,
            "transfer_monitor_mediaservers": self._transfer_monitor_mediaservers or [],
            "timing_full_sync_strm": self._timing_full_sync_strm,
            "full_sync_auto_download_mediainfo_enabled": self._full_sync_auto_download_mediainfo_enabled,
            "cron_full_sync_strm": self._cron_full_sync_strm or "0 */7 * * *",
            "full_sync_strm_paths": self._full_sync_strm_paths or "",
            "monitor_life_enabled": self._monitor_life_enabled,
            "monitor_life_auto_download_mediainfo_enabled": self._monitor_life_auto_download_mediainfo_enabled,
            "monitor_life_paths": self._monitor_life_paths or "",
            "monitor_life_mp_mediaserver_paths": self._monitor_life_mp_mediaserver_paths
            or "",
            "monitor_life_media_server_refresh_enabled": self._monitor_life_media_server_refresh_enabled,
            "monitor_life_mediaservers": self._monitor_life_mediaservers or [],
            "monitor_life_auto_remove_local_enabled": self._monitor_life_auto_remove_local_enabled,
            "monitor_life_scrape_metadata_enabled": self._monitor_life_scrape_metadata_enabled,
            "monitor_life_scrape_metadata_exclude_paths": self._monitor_life_scrape_metadata_exclude_paths
            or "",
            "share_strm_auto_download_mediainfo_enabled": self._share_strm_auto_download_mediainfo_enabled,
            "user_share_code": self._user_share_code or "",
            "user_receive_code": self._user_receive_code or "",
            "user_share_link": self._user_share_link or "",
            "user_share_pan_path": self._user_share_pan_path or "/",
            "user_share_local_path": self._user_share_local_path or "",
            "clear_recyclebin_enabled": self._clear_recyclebin_enabled,
            "clear_receive_path_enabled": self._clear_receive_path_enabled,
            "cron_clear": self._cron_clear or "0 */7 * * *",
            "pan_transfer_enabled": self._pan_transfer_enabled,
            "pan_transfer_paths": self._pan_transfer_paths or "",
            # 获取可用的媒体服务器配置
            "mediaservers": [
                {"title": config.name, "value": config.name}
                for config in self.mediaserver_helper.get_configs().values()
            ],
        }

    async def _save_config_api(self, request: Request) -> Dict:
        """
        异步保存配置
        """
        try:
            data = await request.json()
            self._enabled = data.get("enabled", False)
            self._notify = data.get("notify", False)
            self._strm_url_format = data.get("strm_url_format", "pickcode")
            self._cookies = data.get("cookies", "")
            self._password = data.get("password", "")
            self.moviepilot_address = data.get("moviepilot_address", "")
            self._user_rmt_mediaext = data.get(
                "user_rmt_mediaext",
                "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
            )
            self._user_download_mediaext = data.get(
                "user_download_mediaext", "srt,ssa,ass"
            )
            self._transfer_monitor_enabled = data.get("transfer_monitor_enabled", False)
            self._transfer_monitor_scrape_metadata_enabled = data.get(
                "transfer_monitor_scrape_metadata_enabled", False
            )
            self._transfer_monitor_scrape_metadata_exclude_paths = data.get(
                "transfer_monitor_scrape_metadata_exclude_paths", ""
            )
            self._transfer_monitor_paths = data.get("transfer_monitor_paths", "")
            self._transfer_mp_mediaserver_paths = data.get(
                "transfer_mp_mediaserver_paths", ""
            )
            self._transfer_monitor_media_server_refresh_enabled = data.get(
                "transfer_monitor_media_server_refresh_enabled", False
            )
            self._transfer_monitor_mediaservers = data.get(
                "transfer_monitor_mediaservers", []
            )
            self._timing_full_sync_strm = data.get("timing_full_sync_strm", False)
            self._full_sync_auto_download_mediainfo_enabled = data.get(
                "full_sync_auto_download_mediainfo_enabled", False
            )
            self._cron_full_sync_strm = data.get("cron_full_sync_strm", "0 */7 * * *")
            self._full_sync_strm_paths = data.get("full_sync_strm_paths", "")
            self._monitor_life_enabled = data.get("monitor_life_enabled", False)
            self._monitor_life_auto_download_mediainfo_enabled = data.get(
                "monitor_life_auto_download_mediainfo_enabled", False
            )
            self._monitor_life_paths = data.get("monitor_life_paths", "")
            self._monitor_life_mp_mediaserver_paths = data.get(
                "monitor_life_mp_mediaserver_paths", ""
            )
            self._monitor_life_media_server_refresh_enabled = data.get(
                "monitor_life_media_server_refresh_enabled", False
            )
            self._monitor_life_mediaservers = data.get("monitor_life_mediaservers", [])
            self._monitor_life_auto_remove_local_enabled = data.get(
                "monitor_life_auto_remove_local_enabled", False
            )
            self._monitor_life_scrape_metadata_enabled = data.get(
                "monitor_life_scrape_metadata_enabled", False
            )
            self._monitor_life_scrape_metadata_exclude_paths = data.get(
                "monitor_life_scrape_metadata_exclude_paths", ""
            )
            self._share_strm_auto_download_mediainfo_enabled = data.get(
                "share_strm_auto_download_mediainfo_enabled", False
            )
            self._user_share_code = data.get("user_share_code", "")
            self._user_receive_code = data.get("user_receive_code", "")
            self._user_share_link = data.get("user_share_link", "")
            self._user_share_pan_path = data.get("user_share_pan_path", "/")
            self._user_share_local_path = data.get("user_share_local_path", "")
            self._clear_recyclebin_enabled = data.get("clear_recyclebin_enabled", False)
            self._clear_receive_path_enabled = data.get(
                "clear_receive_path_enabled", False
            )
            self._cron_clear = data.get("cron_clear", "0 */7 * * *")
            self._pan_transfer_enabled = data.get("pan_transfer_enabled", False)
            self._pan_transfer_paths = data.get("pan_transfer_paths", "")

            # 持久化存储配置
            self.__update_config()

            # 重新初始化插件
            self.init_plugin(config=self.get_config())

            return {"code": 0, "msg": "保存成功"}
        except Exception as e:
            return {"code": 1, "msg": f"保存失败: {str(e)}"}

    def _get_status_api(self) -> Dict:
        """
        获取插件状态
        """
        return {
            "code": 0,
            "data": {
                "enabled": self._enabled,
                "has_client": bool(self._client),
                "running": (
                    bool(self._scheduler.get_jobs()) if self._scheduler else False
                )
                or bool(
                    self.monitor_life_thread and self.monitor_life_thread.is_alive()
                ),
            },
        }

    def _trigger_full_sync_api(self) -> Dict:
        """
        触发全量同步
        """
        try:
            if not self._enabled or not self._cookies:
                return {"code": 1, "msg": "插件未启用或未配置cookie"}

            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.full_sync_strm_files,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ))
                + timedelta(seconds=3),
                name="115网盘助手全量生成STRM",
            )
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

            return {"code": 0, "msg": "全量同步任务已启动"}
        except Exception as e:
            return {"code": 1, "msg": f"启动全量同步任务失败: {str(e)}"}

    def _trigger_share_sync_api(self) -> Dict:
        """
        触发分享同步
        """
        try:
            if not self._enabled or not self._cookies:
                return {"code": 1, "msg": "插件未启用或未配置cookie"}

            if not self._user_share_link and not (
                self._user_share_code and self._user_receive_code
            ):
                return {"code": 1, "msg": "未配置分享链接或分享码"}

            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.share_strm_files,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ))
                + timedelta(seconds=3),
                name="115网盘助手分享生成STRM",
            )
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

            return {"code": 0, "msg": "分享同步任务已启动"}
        except Exception as e:
            return {"code": 1, "msg": f"启动分享同步任务失败: {str(e)}"}

    @cached(cache=TTLCache(maxsize=64, ttl=2 * 60))
    def _browse_dir_api(self, request: Request) -> Dict:
        """
        浏览目录
        """
        path = Path(request.query_params.get("path", "/"))
        is_local = request.query_params.get("is_local", "false").lower() == "true"
        if is_local:
            try:
                if not path.exists():
                    return {"code": 1, "msg": f"目录不存在: {path}"}
                dirs = []
                files = []
                for item in path.iterdir():
                    if item.is_dir():
                        dirs.append(
                            {"name": item.name, "path": str(item), "is_dir": True}
                        )
                    else:
                        files.append(
                            {"name": item.name, "path": str(item), "is_dir": False}
                        )
                return {
                    "code": 0,
                    "path": path,
                    "items": sorted(dirs, key=lambda x: x["name"]),
                }
            except Exception as e:
                return {"code": 1, "msg": f"浏览本地目录失败: {str(e)}"}
        else:
            if not self._client or not self._cookies:
                return {"code": 1, "msg": "未配置cookie或客户端初始化失败"}

            try:
                dir_info = self._client.fs_dir_getid(str(path))
                if not dir_info:
                    return {"code": 1, "msg": f"获取目录ID失败: {path}"}
                cid = int(dir_info["id"])

                items = []
                fs_data = self._client.fs_files(cid)
                for item in fs_data["data"]:
                    if "fc" in item:
                        items.append(
                            {
                                "name": item.get("n"),
                                "path": f"{str(path).rstrip('/')}/{item.get('n')}",
                                "is_dir": True,
                            }
                        )
                return {
                    "code": 0,
                    "path": str(path),
                    "items": sorted(items, key=lambda x: x["name"]),
                }
            except Exception as e:
                logger.error(f"浏览网盘目录 API 原始错误: {str(e)}")
                return {"code": 1, "msg": f"浏览网盘目录失败: {str(e)}"}

    def _get_qrcode_api(
        self, request: Request = None, client_type_override: Optional[str] = None
    ) -> Dict:
        """
        获取登录二维码
        """
        try:
            final_client_type = client_type_override
            if not final_client_type:
                final_client_type = (
                    request.query_params.get("client_type", "alipaymini")
                    if request
                    else "alipaymini"
                )
            # 二维码支持的客户端类型验证
            allowed_types = [
                "web",
                "android",
                "115android",
                "ios",
                "115ios",
                "alipaymini",
                "wechatmini",
                "115ipad",
                "tv",
                "qandroid",
            ]
            if final_client_type not in allowed_types:
                final_client_type = "alipaymini"

            logger.info(f"【扫码登入】二维码API - 使用客户端类型: {final_client_type}")

            resp = requests.get(
                "https://qrcodeapi.115.com/api/1.0/web/1.0/token/", timeout=10
            )
            if not resp.ok:
                error_msg = f"获取二维码token失败: {resp.status_code} - {resp.text}"
                return {
                    "code": -1,
                    "error": error_msg,
                    "message": error_msg,
                    "success": False,
                }
            resp_info = resp.json().get("data", {})
            uid = resp_info.get("uid", "")
            _time = resp_info.get("time", "")
            sign = resp_info.get("sign", "")

            resp = requests.get(
                f"https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid={uid}",
                timeout=10,
            )
            if not resp.ok:
                error_msg = f"获取二维码图片失败: {resp.status_code} - {resp.text}"
                return {
                    "code": -1,
                    "error": error_msg,
                    "message": error_msg,
                    "success": False,
                }

            qrcode_base64 = base64.b64encode(resp.content).decode("utf-8")

            tips_map = {
                "alipaymini": "请使用115客户端或支付宝扫描二维码登录",
                "wechatmini": "请使用115客户端或微信扫描二维码登录",
                "android": "请使用115安卓客户端扫描登录",
                "115android": "请使用115安卓客户端扫描登录",
                "ios": "请使用115 iOS客户端扫描登录",
                "115ios": "请使用115 iOS客户端扫描登录",
                "web": "请使用115网页版扫码登录",
                "115ipad": "请使用115 PAD客户端扫描登录",
                "tv": "请使用115 TV客户端扫描登录",
                "qandroid": "请使用115 qandroid客户端扫描登录",
            }
            tips = tips_map.get(final_client_type, "请扫描二维码登录")

            return {
                "code": 0,
                "uid": uid,
                "time": _time,
                "sign": sign,
                "qrcode": f"data:image/png;base64,{qrcode_base64}",
                "tips": tips,
                "client_type": final_client_type,
                "success": True,
            }

        except Exception as e:
            logger.error(f"【扫码登入】获取二维码异常: {e}", exc_info=True)
            return {
                "code": -1,
                "error": f"获取登录二维码出错: {str(e)}",
                "message": f"获取登录二维码出错: {str(e)}",
                "success": False,
            }

    def _check_qrcode_api_internal(
        self,
        uid: str,
        _time: str,
        sign: str,
        client_type: str,
    ) -> Dict:
        """
        检查二维码状态并处理登录
        """
        try:
            if not uid:
                error_msg = "无效的二维码ID，参数uid不能为空"
                return {"code": -1, "error": error_msg, "message": error_msg}

            resp = requests.get(
                f"https://qrcodeapi.115.com/get/status/?uid={uid}&time={_time}&sign={sign}",
                timeout=10,
            )
            status_code = resp.json().get("data").get("status")
        except Exception as e:
            error_msg = f"检查二维码状态异常: {str(e)}"
            logger.error(f"【扫码登入】检查二维码状态异常: {e}", exc_info=True)
            return {"code": -1, "error": error_msg, "message": error_msg}

        status_map = {
            0: {"code": 0, "status": "waiting", "msg": "等待扫码"},
            1: {"code": 0, "status": "scanned", "msg": "已扫码，等待确认"},
            2: {"code": 0, "status": "success", "msg": "已确认，正在登录"},
            -1: {"code": -1, "error": "二维码已过期", "message": "二维码已过期"},
            -2: {"code": -1, "error": "用户取消登录", "message": "用户取消登录"},
        }

        if status_code in status_map:
            result = status_map[status_code].copy()
            if status_code == 2:
                try:
                    resp = requests.post(
                        f"https://passportapi.115.com/app/1.0/{client_type}/1.0/login/qrcode/",
                        data={"app": client_type, "account": uid},
                        timeout=10,
                    )
                    login_data = resp.json()
                except Exception as e:
                    return {
                        "code": -1,
                        "error": f"获取登录结果请求失败: {e}",
                        "message": f"获取登录结果请求失败: {e}",
                    }

                if login_data.get("state") and login_data.get("data"):
                    cookie_data = login_data.get("data", {})
                    cookie_string = ""
                    if "cookie" in cookie_data and isinstance(
                        cookie_data["cookie"], dict
                    ):
                        for name, value in cookie_data["cookie"].items():
                            if name and value:
                                cookie_string += f"{name}={value}; "
                    if cookie_string:
                        self._cookies = cookie_string.strip()
                        self.__update_config()
                        try:
                            self._client = P115Client(self._cookies)
                            result["cookie"] = cookie_string
                        except Exception as ce:
                            return {
                                "code": -1,
                                "error": f"Cookie获取成功，但客户端初始化失败: {str(ce)}",
                                "message": f"Cookie获取成功，但客户端初始化失败: {str(ce)}",
                            }
                    else:
                        return {
                            "code": -1,
                            "error": "登录成功但未能正确解析Cookie",
                            "message": "登录成功但未能正确解析Cookie",
                        }
                else:
                    specific_error = login_data.get(
                        "message", login_data.get("error", "未知错误")
                    )
                    return {
                        "code": -1,
                        "error": f"获取登录会话数据失败: {specific_error}",
                        "message": f"获取登录会话数据失败: {specific_error}",
                    }
            return result
        elif status_code is None:
            return {
                "code": -1,
                "error": "无法解析二维码状态",
                "message": "无法解析二维码状态",
            }
        else:
            return {
                "code": -1,
                "error": f"未知的115业务状态码: {status_code}",
                "message": f"未知的115业务状态码: {status_code}",
            }

    def _check_qrcode_api(self, request: Request) -> dict:
        """
        检查二维码状态
        """
        uid = request.query_params.get("uid", "")
        _time = request.query_params.get("time", "")
        sign = request.query_params.get("sign", "")
        client_type = request.query_params.get("client_type", "alipaymini")
        return self._check_qrcode_api_internal(
            uid=uid, _time=_time, sign=sign, client_type=client_type
        )
