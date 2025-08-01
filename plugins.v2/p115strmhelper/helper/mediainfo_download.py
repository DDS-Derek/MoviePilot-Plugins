import time
from pathlib import Path
from typing import List, cast
from errno import EIO, ENOENT
from urllib.parse import unquote, urlsplit

import requests
from orjson import dumps, loads
from p115rsacipher import encrypt, decrypt

from app.log import logger

from ..core.config import configer
from ..utils.http import check_response
from ..utils.url import Url
from ..utils.sentry import capture_all_class_exceptions


@capture_all_class_exceptions
class MediaInfoDownloader:
    """
    媒体信息文件下载器
    """

    def __init__(self, cookie: str):
        self.cookie = cookie
        self.headers = {
            "User-Agent": configer.get_user_agent(),
            "Cookie": self.cookie,
        }

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

    def get_download_url(self, pickcode: str):
        """
        获取下载链接
        """
        resp = requests.post(
            "http://proapi.115.com/android/2.0/ufile/download",
            data={"data": encrypt(f'{{"pick_code":"{pickcode}"}}').decode("utf-8")},
            headers=self.headers,
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
            headers=self.headers,
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
            headers=self.headers,
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
