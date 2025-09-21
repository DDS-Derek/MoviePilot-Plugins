import shutil
import logging
from io import BytesIO
from pathlib import Path
import posixpath
from posixpath import splitext
from typing import Mapping, Optional, Dict, Union

from encode_uri import encode_uri_component_loose
from property import locked_cacheproperty

from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.dav_error import DAVError, HTTP_NOT_FOUND, HTTP_CREATED
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider

from app.core.config import settings

from ...core.config import configer
from ...db_manager.oper import FileDbHelper
from ...utils.strm import StrmGenerater


logger = logging.getLogger(__name__)


class UTF8PathCorrectionMiddleware:
    """
    UTF-8路径修正中间件
    解决WebDAV中文路径编码问题
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        try:
            corrected_path = path_info.encode("latin-1").decode("utf-8")
            if path_info != corrected_path:
                environ["PATH_INFO"] = corrected_path
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        return self.app(environ, start_response)


class WebDAVResourceBase:
    """
    WebDAV资源基类
    """

    def __init__(self, path: str, environ: dict, attr: Mapping):
        self.path = path
        self.environ = environ
        self.attr = attr

    def __getattr__(self, attr: str):
        """
        动态获取属性
        """
        try:
            return self.attr[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    @locked_cacheproperty
    def mtime(self) -> float:
        """
        修改时间
        """
        return self.attr.get("mtime", 0)

    @locked_cacheproperty
    def name(self) -> str:
        """
        资源名称
        """
        return self.attr["name"]

    @locked_cacheproperty
    def size(self) -> int:
        """
        资源大小
        """
        return self.attr.get("size", 0)

    @locked_cacheproperty
    def is_collection(self) -> bool:
        """
        是否为集合（文件夹）
        """
        return self.attr.get("is_dir", False)

    def get_display_name(self) -> str:
        """
        显示名称
        """
        return self.name

    def get_etag(self) -> str:
        """
        ETag
        """
        return f"{self.attr.get('id', id(self))}-{self.mtime}-{self.size}"

    def get_last_modified(self) -> float:
        """
        最后修改时间
        """
        return self.mtime

    def is_link(self) -> bool:
        """
        是否为链接
        """
        return False

    def support_etag(self) -> bool:
        """
        是否支持ETag
        """
        return True

    def support_modified(self) -> bool:
        """
        是否支持修改时间
        """
        return True


class WebDAVFileResource(WebDAVResourceBase, DAVNonCollection):
    """
    WebDAV文件资源
    支持115网盘文件和本地文件
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        attr: Mapping,
        is_strm: bool = False,
        is_media_info: bool = False,
        local_path: Optional[str] = None,
        provider=None,
        is_pan_file: bool = False,
    ):
        super().__init__(path, environ, attr)
        self.is_strm = is_strm
        self.is_media_info = is_media_info
        self.local_path = local_path
        self.provider = provider
        self.is_pan_file = is_pan_file

    @locked_cacheproperty
    def size(self) -> int:
        """
        文件大小
        """
        if self.is_strm:
            return len(self.strm_data)
        elif self.local_path and Path(self.local_path).exists():
            return Path(self.local_path).stat().st_size
        return self.attr.get("size", 0)

    @locked_cacheproperty
    def strm_data(self) -> bytes:
        """
        STRM文件内容
        """
        if not self.is_strm:
            return b""

        name = encode_uri_component_loose(self.attr["name"])
        moviepilot_address = getattr(configer, "moviepilot_address", "").rstrip("/")
        url = (
            f"{moviepilot_address}/api/v1/plugin/P115StrmHelper/redirect_url"
            f"?apikey={settings.API_TOKEN}&pickcode={self.attr['pickcode']}&file_name={name}"
        )
        return url.encode("utf-8")

    @locked_cacheproperty
    def url(self) -> str:
        """
        文件URL
        """
        name = encode_uri_component_loose(self.attr["name"])
        moviepilot_address = getattr(configer, "moviepilot_address", "").rstrip("/")
        return (
            f"{moviepilot_address}/api/v1/plugin/P115StrmHelper/redirect_url"
            f"?apikey={settings.API_TOKEN}&pickcode={self.attr['pickcode']}&file_name={name}"
        )

    # TODO 待重构
    def get_content(self):
        """
        获取文件内容
        """
        try:
            if self.is_strm:
                return BytesIO(self.strm_data)
            elif self.local_path and Path(self.local_path).exists():
                return open(self.local_path, "rb")
            else:
                try:
                    import requests

                    response = requests.get(self.url, stream=True, timeout=30)
                    response.raise_for_status()
                    import tempfile

                    temp_file = tempfile.NamedTemporaryFile(delete=False)
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                    temp_file.close()

                    return open(temp_file.name, "rb")
                except Exception as download_error:
                    placeholder_content = f"# Cloud Drive File (Download Failed)\n# Original URL: {self.url}\n# Error: {download_error}\n# Please try accessing the file directly.\n".encode(
                        "utf-8"
                    )
                    return BytesIO(placeholder_content)
        except Exception as e:
            raise DAVError(500, f"Error reading content: {e}") from e

    def begin_write(self, *, content_type=None):
        """
        开始写入
        """
        if self.is_pan_file:
            raise DAVError(403, "Cannot write to cloud drive file (read-only)")

        if not self.local_path:
            raise DAVError(403, "Cannot write to a file without a local path")

        try:
            local_file_path = Path(self.local_path)
            local_file_path.parent.mkdir(parents=True, exist_ok=True)

            content_length = int(self.environ.get("CONTENT_LENGTH", 0))
            if content_length == 0:
                local_file_path.touch()
                local_file_path.chmod(0o644)

                self.attr["mtime"] = local_file_path.stat().st_mtime
                self.attr["size"] = 0

                parent_resource = self.provider.get_resource_inst(
                    posixpath.dirname(self.path), self.environ
                )
                if parent_resource and hasattr(parent_resource, "_children_cache"):
                    del parent_resource._children_cache

                return BytesIO()
            else:
                wsgi_input = self.environ.get("wsgi.input")
                if not wsgi_input:
                    raise DAVError(500, "Could not get wsgi.input from environ.")

                bytes_written = 0
                with open(local_file_path, "wb") as f:
                    if content_length > 0:
                        remaining = content_length
                        while remaining > 0:
                            chunk_size = min(remaining, 1024 * 1024)
                            chunk = wsgi_input.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            remaining -= len(chunk)
                            bytes_written += len(chunk)
                    else:
                        while True:
                            chunk = wsgi_input.read(1024 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            bytes_written += len(chunk)
                self.attr["mtime"] = local_file_path.stat().st_mtime
                self.attr["size"] = local_file_path.stat().st_size
                local_file_path.chmod(0o644)
                raise DAVError(HTTP_CREATED)
        except DAVError:
            raise
        except Exception as e:
            logger.error(
                f"Error during self-managed write for {self.local_path}: {e}",
                exc_info=True,
            )
            raise DAVError(500, f"Error during file write operation: {e}") from e

    def end_write(self, *, with_errors):
        """
        结束写入
        """
        if not with_errors and self.local_path:
            try:
                local_file_path = Path(self.local_path)
                local_file_path.chmod(0o644)
                self.attr["mtime"] = local_file_path.stat().st_mtime
                self.attr["size"] = local_file_path.stat().st_size
            except Exception as e:
                logger.error(f"Failed to finalize write {self.local_path}: {e}")
                raise DAVError(500, f"Error completing write: {e}") from e

    def get_content_length(self) -> int:
        """
        内容长度
        """
        return self.size

    def support_content_length(self) -> bool:
        """
        是否支持内容长度
        """
        return True

    def support_ranges(self) -> bool:
        """
        是否支持范围请求
        """
        return not self.is_strm

    def delete(self):
        """
        删除文件
        """
        if self.is_pan_file:
            raise DAVError(403, "Cannot delete cloud drive file (read-only)")

        if not self.local_path:
            raise DAVError(403, "Cannot delete file without a local path")

        try:
            local_file_path = Path(self.local_path)
            if local_file_path.exists():
                local_file_path.unlink()
            return True
        except Exception as e:
            raise DAVError(500, f"Error deleting file: {e}") from e

    def move_recursive(self, dest_path: str):
        """
        移动文件
        """
        if self.is_pan_file:
            raise DAVError(403, "Cannot move cloud drive file (read-only)")

        if not self.local_path:
            raise DAVError(403, "Cannot move file without a local path")
        if not self.provider:
            raise DAVError(500, "Provider not available for path resolution")

        dest_local_path = self.provider._get_local_path_from_dav(dest_path)

        if dest_local_path.exists():
            raise DAVError(405, "Destination already exists.")

        try:
            source_path = Path(self.local_path)
            dest_local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_path), str(dest_local_path))
            return True
        except Exception as e:
            raise DAVError(500, f"Error moving file: {e}") from e

    def is_readonly(self) -> bool:
        """
        是否只读
        """
        return self.is_pan_file


class WebDAVFolderResource(WebDAVResourceBase, DAVCollection):
    """
    WebDAV文件夹资源
    支持115网盘文件夹和本地文件夹的混合
    """

    def __init__(
        self,
        path: str,
        environ: dict,
        attr: Mapping,
        local_mapping_path: Optional[str] = None,
        provider=None,
        is_pan_folder: bool = False,
    ):
        super().__init__(path, environ, attr)
        self.local_mapping_path = local_mapping_path
        self.provider = provider
        self.is_pan_folder = is_pan_folder
        self.attr["is_dir"] = True

    def is_readonly(self) -> bool:
        return False

    @locked_cacheproperty
    def children(self) -> Dict[str, Union[WebDAVFileResource, "WebDAVFolderResource"]]:
        """
        子资源
        """
        children = {}
        dir_path = posixpath.join(self.path, "")

        pan_children = self._get_pan_children(dir_path, self.environ)

        local_children = self._get_local_children(dir_path, self.environ)

        for name, pan_resource in pan_children.items():
            if not self._is_media_info_file(name):
                children[name] = pan_resource

        for name, local_resource in local_children.items():
            if self._is_media_info_file(name):
                children[name] = local_resource
            else:
                # 非媒体信息文件，如果网盘没有则添加本地文件
                if name not in children:
                    children[name] = local_resource

        return children

    def _get_pan_children(
        self, dir_path: str, environ: dict
    ) -> Dict[str, Union[WebDAVFileResource, "WebDAVFolderResource"]]:
        """
        获取115网盘子资源
        """
        children = {}
        try:
            folder_id_str = str(self.attr["id"])
            if folder_id_str.startswith("local_"):
                return children

            folder_id = int(folder_id_str)
            if folder_id == 0 and dir_path != "/":
                return children

            db_helper = FileDbHelper()
            children_data = db_helper.get_webdav_children(folder_id)

            for folder_data in children_data.get("subfolders", []):
                original_name = folder_data["name"]
                safe_name = original_name.replace("/", "|")
                path = posixpath.join(dir_path, safe_name)
                folder_attr = {
                    "id": folder_data["id"],
                    "name": original_name,
                    "is_dir": True,
                    "mtime": 0,
                    "size": 0,
                }
                local_mapping = (
                    self.provider._get_local_path_from_dav(path)
                    if self.provider
                    else None
                )
                children[safe_name] = WebDAVFolderResource(
                    path,
                    environ,
                    folder_attr,
                    str(local_mapping) if local_mapping else None,
                    self.provider,
                    is_pan_folder=True,
                )

            # 处理文件
            for file_data in children_data.get("files", []):
                original_name = file_data["name"]
                safe_name = original_name.replace("/", "|")
                display_name = safe_name
                is_strm = self._should_be_strm(original_name, file_data["size"])
                if is_strm:
                    display_name = splitext(safe_name)[0] + ".strm"

                path = posixpath.join(dir_path, display_name)
                file_attr = {
                    "id": file_data["id"],
                    "name": original_name,
                    "pickcode": file_data["pickcode"],
                    "is_dir": False,
                    "mtime": file_data["mtime"],
                    "size": file_data["size"],
                }
                children[display_name] = WebDAVFileResource(
                    path,
                    environ,
                    file_attr,
                    is_strm=is_strm,
                    is_media_info=False,
                    local_path=None,
                    provider=self.provider,
                    is_pan_file=True,
                )
        except Exception as e:
            logger.error("Failed to get cloud drive items for %s: %s", dir_path, e)

        return children

    def _get_local_children(
        self, dir_path: str, environ: dict
    ) -> Dict[str, Union[WebDAVFileResource, "WebDAVFolderResource"]]:
        """
        获取本地子资源
        """
        children = {}
        if not self.local_mapping_path:
            return children

        local_path = Path(self.local_mapping_path)

        try:
            local_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(
                "Failed to create local mapping directory %s: %s", local_path, e
            )
            return children

        try:
            for item_path in local_path.iterdir():
                name = item_path.name
                path = posixpath.join(dir_path, name)

                # 跳过系统文件
                if name.startswith("._") or name == ".DS_Store":
                    continue

                if item_path.is_file():
                    file_attr = {
                        "id": f"local_{hash(str(item_path))}",
                        "name": name,
                        "is_dir": False,
                        "mtime": item_path.stat().st_mtime,
                        "size": item_path.stat().st_size,
                    }
                    children[name] = WebDAVFileResource(
                        path,
                        environ,
                        file_attr,
                        is_strm=False,
                        is_media_info=self._is_media_info_file(name),
                        local_path=str(item_path),
                        provider=self.provider,
                        is_pan_file=False,
                    )
                elif item_path.is_dir():
                    folder_attr = {
                        "id": f"local_folder_{hash(str(item_path))}",
                        "name": name,
                        "is_dir": True,
                        "mtime": item_path.stat().st_mtime,
                        "size": 0,
                    }
                    children[name] = WebDAVFolderResource(
                        path,
                        environ,
                        folder_attr,
                        str(item_path),
                        self.provider,
                        is_pan_folder=False,
                    )

        except Exception as e:
            logger.error("Error scanning local path %s: %s", self.local_mapping_path, e)

        return children

    def _should_be_strm(self, filename: str, filesize: Optional[int] = None) -> bool:
        """
        判断是否应该生成STRM文件
        """
        user_rmt_mediaext = getattr(configer, "user_rmt_mediaext", "")
        if user_rmt_mediaext:
            media_extensions = {
                f".{ext.strip()}"
                for ext in user_rmt_mediaext.replace("，", ",").split(",")
            }
            if not any(filename.lower().endswith(ext) for ext in media_extensions):
                return False

        min_file_size = getattr(configer, "full_sync_min_file_size", None)
        if filesize and min_file_size and filesize < min_file_size:
            return False

        _, should_generate = StrmGenerater.should_generate_strm(
            filename, "full", filesize
        )
        return should_generate

    def _is_media_info_file(self, filename: str) -> bool:
        """
        判断是否为媒体信息文件
        """
        user_download_mediaext = getattr(configer, "user_download_mediaext", "")
        if not user_download_mediaext:
            return False

        media_info_extensions = {
            f".{ext.strip()}"
            for ext in user_download_mediaext.replace("，", ",").split(",")
        }
        return any(filename.lower().endswith(ext) for ext in media_info_extensions)

    def support_recursive_move(self, dest_path: str) -> bool:
        """
        告诉框架我们支持一个高效的、原生的移动实现
        """
        return bool(self.local_mapping_path)

    def move_recursive(self, dest_path: str):
        """
        实现一个高效的、基于本地文件系统的原子重命名操作
        """
        if not self.local_mapping_path:
            raise DAVError(403, "Cannot move a resource without a local mapping path.")

        if not self.provider:
            raise DAVError(500, "Provider not available for path resolution.")

        source_local_path = Path(self.local_mapping_path)
        dest_local_path = self.provider._get_local_path_from_dav(dest_path)

        if not source_local_path.exists():
            raise DAVError(
                404, "Source resource does not exist on the local file system."
            )

        if dest_local_path.exists():
            raise DAVError(412, "Destination resource already exists.")

        try:
            dest_local_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source_local_path), str(dest_local_path))

            parent_dav_path = posixpath.dirname(self.path)
            parent_resource = self.provider.get_resource_inst(
                parent_dav_path, self.environ
            )
            if parent_resource and hasattr(parent_resource, "_children_cache"):
                del parent_resource._children_cache
                logger.warning(
                    f"Cache for parent '{parent_resource.path}' invalidated after move."
                )

            dest_parent_dav_path = posixpath.dirname(dest_path)
            if dest_parent_dav_path != parent_dav_path:
                dest_parent_resource = self.provider.get_resource_inst(
                    dest_parent_dav_path, self.environ
                )
                if dest_parent_resource and hasattr(
                    dest_parent_resource, "_children_cache"
                ):
                    del dest_parent_resource._children_cache
                    logger.warning(
                        f"Cache for dest parent '{dest_parent_resource.path}' invalidated after move."
                    )

            return []
        except Exception as e:
            logger.error(f"Error moving directory: {e}", exc_info=True)
            raise DAVError(500, f"Failed to move resource: {e}") from e

    def get_member(
        self, name: str
    ) -> Union[WebDAVFileResource, "WebDAVFolderResource"]:
        """
        获取成员
        """
        if attr := self.children.get(name):
            return attr
        raise DAVError(404, posixpath.join(self.path, name))

    def get_member_list(
        self,
    ) -> list[Union[WebDAVFileResource, "WebDAVFolderResource"]]:
        """
        获取成员列表
        """
        return list(self.children.values())

    def get_member_names(self) -> list[str]:
        """
        获取成员名称列表
        """
        return list(self.children)

    def create_collection(self, name: str):
        """
        创建文件夹
        """
        if not self.local_mapping_path:
            logger.error(
                "Attempted to create collection in a resource with no local mapping path: %s",
                self.path,
            )
            raise DAVError(403, "Cannot create collection: no local mapping path")

        parent_local_path = Path(self.local_mapping_path)
        new_folder_path = parent_local_path / name

        if new_folder_path.exists():
            raise DAVError(405, "Folder already exists.")

        try:
            parent_local_path.mkdir(mode=0o755, parents=True, exist_ok=True)
            parent_local_path.chmod(0o755)

            new_folder_path.mkdir(mode=0o755)
            new_folder_path.chmod(0o755)

            folder_attr = {
                "id": f"local_folder_{hash(str(new_folder_path))}",
                "name": name,
                "is_dir": True,
                "mtime": new_folder_path.stat().st_mtime,
                "size": 0,
            }
            new_path = posixpath.join(self.path, name)
            new_resource = WebDAVFolderResource(
                new_path,
                self.environ,
                folder_attr,
                str(new_folder_path),
                self.provider,
                is_pan_folder=False,
            )

            if hasattr(self, "_children_cache"):
                del self._children_cache

            return new_resource
        except Exception as e:
            logger.error("Failed to create folder %s: %s", new_folder_path, e)
            raise DAVError(500, f"Failed to create folder: {e}") from e

    def create_empty_resource(self, name: str) -> WebDAVFileResource:
        """
        创建空文件
        """
        if not self.local_mapping_path:
            if self.provider:
                local_mapping_path = self.provider._get_local_path_from_dav(self.path)
                self.local_mapping_path = str(local_mapping_path)
                local_mapping_path.mkdir(parents=True, exist_ok=True)
            else:
                raise DAVError(403, "Cannot create file: no local mapping path")

        new_file_path = Path(self.local_mapping_path) / name
        if new_file_path.exists():
            raise DAVError(405, "File already exists.")

        try:
            new_file_path.touch()
            new_file_path.chmod(0o644)

            file_attr = {
                "id": f"local_file_{hash(str(new_file_path))}",
                "name": name,
                "is_dir": False,
                "mtime": new_file_path.stat().st_mtime,
                "size": 0,
            }
            new_path = posixpath.join(self.path, name)
            new_resource = WebDAVFileResource(
                new_path,
                self.environ,
                file_attr,
                is_strm=False,
                is_media_info=self._is_media_info_file(name),
                local_path=str(new_file_path),
                provider=self.provider,
                is_pan_file=False,  # 标记为本地文件
            )

            if hasattr(self, "_children_cache"):
                del self._children_cache
            return new_resource
        except Exception as e:
            raise DAVError(500, f"Failed to create file: {e}") from e

    def delete(self):
        """
        删除文件夹
        """
        if not self.local_mapping_path:
            raise DAVError(403, "Cannot delete cloud drive folder")

        try:
            local_path = Path(self.local_mapping_path)
            if not local_path.exists():
                return True
            if local_path.is_dir():
                shutil.rmtree(local_path)
            else:
                local_path.unlink()
            return True
        except Exception as e:
            raise DAVError(500, f"Error deleting resource: {e}") from e


class WebDAVFileSystemProvider(DAVProvider):
    """
    WebDAV文件系统提供者
    管理混合文件系统的访问
    """

    def __init__(self, local_mapping_path: str):
        super().__init__()
        self.local_mapping_path = Path(local_mapping_path).resolve()
        self.local_mapping_path.mkdir(parents=True, exist_ok=True)

    def _get_local_path_from_dav(self, path: str) -> Path:
        """
        从WebDAV路径获取本地路径
        """
        try:
            import urllib.parse

            decoded_path = urllib.parse.unquote(path)
        except Exception:
            decoded_path = path

        path = decoded_path.strip("/")
        safe_path = Path(path).as_posix()
        if ".." in safe_path.split("/"):
            raise DAVError(400, "Invalid path with '..'")
        return self.local_mapping_path / safe_path

    def get_resource_inst(
        self, path: str, environ: dict
    ) -> Union[WebDAVFolderResource, WebDAVFileResource, None]:
        """
        获取资源实例
        """
        norm_path = posixpath.normpath(posixpath.join("/", path))

        root_attr = {"id": 0, "name": "root", "is_dir": True, "mtime": 0, "size": 0}
        current_res = WebDAVFolderResource(
            "/",
            environ,
            root_attr,
            str(self.local_mapping_path),
            provider=self,
            is_pan_folder=True,
        )

        if norm_path == "/":
            return current_res

        parts = norm_path.strip("/").split("/")
        for i, part in enumerate(parts):
            if not part:
                continue

            if part.startswith("._") or part == ".DS_Store":
                raise DAVError(404, norm_path)

            if not isinstance(current_res, DAVCollection):
                return None

            try:
                current_res = current_res.get_member(part)

            except DAVError as e:
                if e.value == HTTP_NOT_FOUND:
                    return None
                raise e

        return current_res

    def is_readonly(self) -> bool:
        """
        是否只读
        """
        return False


def create_hybrid_webdav_app(local_mapping_path: str):
    """
    创建混合WebDAV应用
    """
    local_path = Path(local_mapping_path)
    local_path.mkdir(mode=0o755, parents=True, exist_ok=True)

    # WebDAV配置
    config = {
        "provider_mapping": {"/": WebDAVFileSystemProvider(local_mapping_path)},
        "simple_dc": {"user_mapping": {"*": True}},
        "verbose": 5,
        "hotfixes": {
            "emulate_win32_lastmod": False,
            "unquote_path_info": False,
            "re_encode_path_info": False,
        },
        "browser": {"enable": True, "browseable": True},
        "logging": {"enable": True, "level": "WARNING"},
        "dav_methods": {
            "MKCOL": True,
            "PROPFIND": True,
            "PROPPATCH": True,
            "GET": True,
            "PUT": True,
            "DELETE": True,
            "COPY": True,
            "MOVE": True,
        },
    }

    app = WsgiDAVApp(config)

    return UTF8PathCorrectionMiddleware(app)
