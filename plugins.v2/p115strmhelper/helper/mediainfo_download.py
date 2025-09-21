import asyncio
import time
from itertools import batched
from pathlib import Path
from uuid import uuid4
from typing import List, cast, Dict, Set
from errno import EIO, ENOENT
from urllib.parse import unquote, urlsplit

import aiofiles
import aiofiles.os
import httpx
from orjson import dumps, loads
from p115rsacipher import encrypt, decrypt
from p115pickcode import pickcode_to_id
from p115client import P115Client, check_response as p115_check_response
from p115client.const import TYPE_TO_SUFFIXES
from p115client.tool.util import reduce_image_url_layers
from p115client.tool.iterdir import _iter_fs_files, iter_files

from app.log import logger

from ..core.config import configer
from ..utils.http import check_response
from ..utils.url import Url
from ..utils.sentry import sentry_manager
from ..utils.exception import DownloadValidationFail


@sentry_manager.capture_all_class_exceptions
class MediaInfoDownloader:
    """
    媒体信息文件下载器
    """

    # 批处理文件数量
    batch_size = 200
    # 最大同时下载线程（cdn_url）
    max_workers = 8

    def __init__(self, cookie: str):
        self.cookie = cookie
        self.client = P115Client(cookie)

        base_headers = {
            "User-Agent": configer.get_user_agent(),
            "Cookie": self.cookie,
        }
        sanitized_headers = {}
        for key, value in base_headers.items():
            if value is None:
                continue
            if isinstance(value, bytes):
                final_value = value.decode("utf-8", errors="ignore")
            else:
                final_value = str(value)
            sanitized_headers[key] = final_value.strip()
        self.headers = sanitized_headers

        self.stop_all_flag = None

        self.mediainfo_count: int = 0
        self.mediainfo_fail_count: int = 0
        self.mediainfo_fail_dict: List = []

        logger.debug(f"【媒体信息文件下载】初始化请求头：{self.headers}")

    @staticmethod
    def is_file_leq_1k(file_path):
        """
        判断文件是否小于 1KB
        """
        file = Path(file_path)
        if not file.exists():
            return True
        return file.stat().st_size <= 1024

    @staticmethod
    async def async_is_file_leq_1k(file_path: str | Path) -> bool:
        """
        判断文件是否小于等于 1KB。

        如果文件不存在，返回 True。
        """
        try:
            stat_result = await aiofiles.os.stat(file_path)
            return stat_result.st_size <= 1024
        except FileNotFoundError:
            return True
        except Exception:
            return False

    def get_download_url(self, pickcode: str):
        """
        获取下载链接
        """
        resp = httpx.post(
            "http://proapi.115.com/android/2.0/ufile/download",
            data={"data": encrypt(f'{{"pick_code":"{pickcode}"}}').decode("utf-8")},
            headers=self.headers,
            follow_redirects=True
        )
        if resp.status_code == 403:
            self.stop_all_flag = True
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
        with httpx.stream(
            "GET",
            download_url,
            timeout=30,
            headers=self.headers,
            follow_redirects=True,
        ) as response:
            if response.status_code == 403:
                self.stop_all_flag = True
            response.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"【媒体信息文件下载】保存 {file_name} 文件成功: {file_path}")

    async def async_save_mediainfo_file(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        file_path: Path,
        file_name: str,
        download_url: str,
        hide_cookies: bool = False,
    ):
        """
        带验证和重试机制的异步下载
        """
        async with semaphore:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    request_headers = self.headers.copy()
                    request_headers["Connection"] = "close"
                    if hide_cookies:
                        request_headers.pop("Cookie")

                    async with client.stream(
                        "GET", download_url, timeout=30, headers=request_headers
                    ) as response:
                        if response.status_code == 403:
                            self.stop_all_flag = True
                            response.raise_for_status()
                        response.raise_for_status()
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        async with aiofiles.open(file_path, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                await f.write(chunk)

                    if await self.async_is_file_leq_1k(file_path):
                        raise DownloadValidationFail(
                            f"【媒体信息文件下载】文件 {file_name} 在下载后验证失败"
                        )

                    logger.info(
                        f"【媒体信息文件下载】保存 {file_name} 成功: {file_path}"
                    )
                    self.mediainfo_count += 1
                    return

                except DownloadValidationFail as e:
                    error_message = str(e)
                except httpx.LocalProtocolError as e:
                    error_message = f"协议错误 (LocalProtocolError): {e}"
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 403:
                        logger.error(
                            f"【下载失败】获取 {file_name} 时被拒绝 (403 Forbidden)，将不会重试。"
                        )
                        return
                    error_message = f"HTTP错误 {e.response.status_code}"
                except httpx.RequestError as e:
                    error_message = f"网络请求错误 {type(e).__name__}"
                except Exception as e:
                    error_message = f"未知错误 {type(e).__name__}: {e}"

                logger.warning(
                    f"【媒体信息文件下载】保存 {file_name} 失败 (尝试 {attempt + 1}/{max_retries})，原因: {error_message}"
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    self.mediainfo_fail_count += 1
                    self.mediainfo_fail_dict.append(file_path.as_posix())
                    logger.error(
                        f"【媒体信息文件下载】保存 {file_name} 在 {max_retries} 次尝试后最终失败"
                    )

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
        resp = httpx.post(
            "http://proapi.115.com/app/share/downurl",
            data={"data": encrypt(dumps(payload)).decode("utf-8")},
            headers=self.headers,
            follow_redirects=True
        )
        if resp.status_code == 403:
            self.stop_all_flag = True
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
        self.stop_all_flag = False
        mediainfo_count: int = 0
        mediainfo_fail_count: int = 0
        mediainfo_fail_dict: List = []
        stop_all_msg_flag = True
        try:
            for item in downloads_list:
                if not item:
                    continue
                if self.stop_all_flag is True:
                    if stop_all_msg_flag:
                        logger.error(
                            "【媒体信息文件下载】触发风控，停止所有媒体信息文件下载"
                        )
                        stop_all_msg_flag = False
                    mediainfo_fail_count += 1
                    mediainfo_fail_dict.append(item["path"])
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

    async def __async_download_batch_subtitle_image(
        self, data_map: Dict[str | int, str], item_list, value: str = "sha1"
    ):
        """
        为单个批次创建并并发执行所有下载任务
        """
        semaphore = asyncio.Semaphore(256)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks = []
            for item in item_list:
                url = data_map.get(item[value])
                if url:
                    path = Path(item["path"])
                    task = self.async_save_mediainfo_file(
                        client,
                        semaphore,
                        path,
                        path.name,
                        url,
                        hide_cookies=bool(value == "sha1"),
                    )
                    tasks.append(task)
            if tasks:
                await asyncio.gather(*tasks)

    def batch_subtitle_downloader(self, downloads_list: List):
        """
        批量字幕文件下载

        .. caution::
            这个函数运行时，会把相关文件以 200 为一批，同一批次复制到同一个新建的目录，在批量获取链接后，自动把目录删除到回收站

        .. attention::
            目前 115 只支持：".srt"、".ass"、".ssa"
        """
        for item_list in batched(downloads_list, self.batch_size):
            resp = self.client.fs_mkdir(
                f"subtitle-{uuid4()}",
            )
            p115_check_response(resp)
            if "cid" in resp:
                scid = resp["cid"]
            else:
                data = resp["data"]
                if "category_id" in data:
                    scid = data["category_id"]
                else:
                    scid = data["file_id"]
            try:
                resp = self.client.fs_copy(
                    [pickcode_to_id(item["pickcode"]) for item in item_list],
                    pid=scid,
                )
                p115_check_response(resp)
                attr = next(
                    _iter_fs_files(
                        client=self.client,
                        payload=scid,
                        page_size=1,
                        app="web",
                    )
                )
                resp = self.client.fs_video_subtitle(
                    attr["pickcode"],
                )
                p115_check_response(resp)
                subtitles = {
                    info["sha1"]: info["url"]
                    for info in resp["data"]["list"]
                    if info.get("file_id")
                }
                asyncio.run(
                    self.__async_download_batch_subtitle_image(subtitles, item_list)
                )
            except Exception as e:
                logger.error(f"【媒体信息文件下载】批处理字幕文件失败: {e}")
            finally:
                self.client.fs_delete(scid)

    def batch_image_downloader(self, downloads_list: List):
        """
        批量图片文件下载

        .. caution::
            这个函数运行时，会把相关文件以 200 为一批，同一批次复制到同一个新建的目录，在批量获取链接后，自动把目录删除到回收站
        """
        for item_list in batched(downloads_list, self.batch_size):
            resp = self.client.fs_mkdir(
                f"image-{uuid4()}",
            )
            p115_check_response(resp)
            scid = resp["cid"]
            try:
                ids = [pickcode_to_id(item["pickcode"]) for item in item_list]
                resp = self.client.fs_copy(
                    ids,
                    pid=scid,
                )
                p115_check_response(resp)
                images: Dict = {}
                for attr in iter_files(
                    client=self.client, cid=scid, cooldown=1.5, type=2
                ):
                    url = None
                    try:
                        url = reduce_image_url_layers(attr["thumb"])
                    except KeyError:
                        if attr.get("is_collect", False):
                            if attr["size"] < 1024 * 1024 * 115:
                                url = self.client.download_url(
                                    attr["pickcode"],
                                    use_web_api=True,
                                )
                        else:
                            url = self.client.download_url(
                                attr["pickcode"],
                            )
                    if url:
                        images[attr["sha1"]] = url
                asyncio.run(
                    self.__async_download_batch_subtitle_image(images, item_list)
                )
            except Exception as e:
                logger.error(f"【媒体信息文件下载】批处理图片文件失败: {e}")
            finally:
                self.client.fs_delete(scid)

    def batch_downloader(self, downloads_list: List, **request_kwargs):
        """
        批处理其它类型文件下载
        """
        if headers := request_kwargs.get("headers"):
            request_kwargs["headers"] = dict(
                headers, **{"user-agent": configer.get_user_agent()}
            )
        else:
            request_kwargs["headers"] = {"user-agent": configer.get_user_agent()}
        for item in downloads_list:
            item["file_id"] = pickcode_to_id(item["pickcode"])
        try:
            for item_list in batched(downloads_list, self.batch_size):
                pcs = [item["pickcode"] for item in item_list]
                resp = self.client.download_urls(",".join(pcs), **request_kwargs)
                data_map = {key: value.geturl() for key, value in resp.items()}
                for batch in batched(item_list, self.max_workers):
                    if self.stop_all_flag:
                        return
                    asyncio.run(
                        self.__async_download_batch_subtitle_image(
                            data_map, batch, "file_id"
                        )
                    )
                    time.sleep(1)
        except Exception as e:
            logger.error(f"【媒体信息文件下载】批处理下载文件失败: {e}")

    def batch_auto_downloader(self, downloads_list: List):
        """
        根据列表自动批量下载
        """
        image_suffix: Set[str] = set(TYPE_TO_SUFFIXES[2])
        subtitle_suffix: Set[str] = {".srt", ".ass", ".ssa"}

        self.stop_all_flag = False
        self.mediainfo_count: int = 0
        self.mediainfo_fail_count: int = 0
        self.mediainfo_fail_dict: List = []

        image_list: List = []
        subtitle_list: List = []
        other_list: List = []
        for item in downloads_list:
            suffix = Path(item["path"]).suffix
            if suffix in subtitle_suffix:
                subtitle_list.append(item)
            elif suffix in image_suffix:
                image_list.append(item)
            else:
                other_list.append(item)
        if subtitle_list and not self.stop_all_flag:
            self.batch_subtitle_downloader(subtitle_list)
        if image_list and not self.stop_all_flag:
            self.batch_image_downloader(image_list)
        if other_list and not self.stop_all_flag:
            self.batch_downloader(other_list)

        return self.mediainfo_count, self.mediainfo_fail_count, self.mediainfo_fail_dict
