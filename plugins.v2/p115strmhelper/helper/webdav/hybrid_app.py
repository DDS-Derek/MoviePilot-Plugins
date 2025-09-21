import os
import time
from io import BytesIO
from os.path import splitext, splitpath
from typing import Mapping, Optional, Union, TYPE_CHECKING
from encode_uri import encode_uri_component_loose
from property import locked_cacheproperty

if TYPE_CHECKING:
    from typing import Dict

from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.dav_error import DAVError
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider

from app.core.config import settings

from ...core.config import configer
from ...db_manager.oper import FileDbHelper
from ...utils.strm import StrmGenerater


class HybridDavPathBase:
    """
    混合WebDAV路径基类
    """

    def __getattr__(self, attr: str, /):
        try:
            return self.attr[attr]
        except KeyError as e:
            raise AttributeError(attr) from e

    @locked_cacheproperty
    def mtime(self, /) -> int | float:
        return self.attr.get("mtime", 0)

    @locked_cacheproperty
    def name(self, /) -> str:
        return self.attr["name"]

    @locked_cacheproperty
    def size(self, /) -> int:
        return self.attr.get("size") or 0

    def get_display_name(self, /) -> str:
        return self.name

    def get_etag(self, /) -> str:
        return "%s-%s-%s" % (
            self.attr["id"],
            self.mtime,
            self.size,
        )

    def get_last_modified(self, /) -> float:
        return self.mtime

    def is_link(self, /) -> bool:
        return False

    def support_etag(self, /) -> bool:
        return True

    def support_modified(self, /) -> bool:
        return True


class HybridFileResource(HybridDavPathBase, DAVNonCollection):
    """
    混合文件资源
    """

    def __init__(
        self,
        /,
        path: str,
        environ: dict,
        attr: Mapping,
        is_strm: bool = False,
        is_media_info: bool = False,
        local_path: Optional[str] = None,
    ):
        super().__init__(path, environ)
        self.attr = attr
        self.is_strm = is_strm
        self.is_media_info = is_media_info
        self.local_path = local_path

    @locked_cacheproperty
    def size(self, /) -> int:
        if self.is_strm:
            return len(self.strm_data)
        elif self.is_media_info and self.local_path and os.path.exists(self.local_path):
            return os.path.getsize(self.local_path)
        return self.attr.get("size", 0)

    @locked_cacheproperty
    def strm_data(self, /) -> bytes:
        """
        生成STRM文件内容
        """
        attr = self.attr
        name = encode_uri_component_loose(attr["name"])
        moviepilot_address = getattr(configer, "moviepilot_address", "")
        if moviepilot_address:
            moviepilot_address = moviepilot_address.rstrip("/")
        url = f"{moviepilot_address}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={attr['pickcode']}&file_name={name}"
        return bytes(url, "utf-8")

    @locked_cacheproperty
    def url(self, /) -> str:
        """
        获取重定向URL
        """
        attr = self.attr
        name = encode_uri_component_loose(attr["name"])
        moviepilot_address = getattr(configer, "moviepilot_address", "")
        if moviepilot_address:
            moviepilot_address = moviepilot_address.rstrip("/")
        return f"{moviepilot_address}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={attr['pickcode']}&file_name={name}"

    def get_content(self, /):
        """
        获取文件内容
        """
        if self.is_strm:
            return BytesIO(self.strm_data)
        elif self.is_media_info and self.local_path and os.path.exists(self.local_path):
            return open(self.local_path, "rb")
        raise DAVError(302, add_headers=[("Location", self.url)])

    def get_content_length(self, /) -> int:
        return self.size

    def support_content_length(self, /) -> bool:
        return True

    def support_ranges(self, /) -> bool:
        return True

    def is_readonly(self, /) -> bool:
        """
        媒体文件只读，媒体信息文件可写
        """
        if self.is_strm:
            return True
        return not self.is_media_info


class HybridFolderResource(HybridDavPathBase, DAVCollection):
    """
    混合文件夹资源
    """

    def __init__(
        self,
        /,
        path: str,
        environ: dict,
        attr: Mapping,
        local_mapping_path: Optional[str] = None,
    ):
        super().__init__(path, environ)
        self.attr = attr
        self.local_mapping_path = local_mapping_path

    @locked_cacheproperty
    def children(
        self, /
    ) -> "Dict[str, Union[HybridFileResource, HybridFolderResource]]":
        """
        获取子项列表，合并网盘数据和本地数据
        """
        children: dict[str, HybridFileResource | HybridFolderResource] = {}
        environ = self.environ
        dir_ = self.path
        if dir_ != "/":
            dir_ += "/"

        # 获取网盘数据
        pan_children = self._get_pan_children(dir_, environ)

        # 获取本地媒体信息文件
        local_children = self._get_local_children(dir_, environ)

        # 合并数据，网盘媒体文件优先，本地媒体信息文件优先
        children.update(pan_children)
        children.update(local_children)

        return children

    def _get_pan_children(
        self, dir_: str, environ: dict
    ) -> "Dict[str, Union[HybridFileResource, HybridFolderResource]]":
        """
        获取网盘子项
        """
        children: "Dict[str, Union[HybridFileResource, HybridFolderResource]]" = {}

        try:
            # 从数据库获取文件夹和文件
            folder_id = int(self.attr["id"])
            db_helper = FileDbHelper()
            children_data = db_helper.get_webdav_children(folder_id)

            # 处理子文件夹
            for folder_data in children_data["subfolders"]:
                name = folder_data["name"].replace("/", "|")
                path = dir_ + name
                folder_attr = {
                    "id": folder_data["id"],
                    "name": folder_data["name"],
                    "is_dir": True,
                    "mtime": 0,
                    "size": 0,
                }
                local_mapping = self._get_local_mapping_path(path)
                children[name] = HybridFolderResource(
                    path, environ, folder_attr, local_mapping
                )

            # 处理子文件
            for file_data in children_data["files"]:
                name = file_data["name"].replace("/", "|")
                is_strm = self._should_be_strm(file_data["name"], file_data["size"])

                if is_strm:
                    name = splitext(name)[0] + ".strm"

                path = dir_ + name
                file_attr = {
                    "id": file_data["id"],
                    "name": file_data["name"],
                    "pickcode": file_data["pickcode"],
                    "is_dir": False,
                    "mtime": file_data["mtime"],
                    "size": file_data["size"],
                }

                # 检查是否有对应的本地媒体信息文件
                self._get_media_info_path(path, file_data["name"])

                children[name] = HybridFileResource(
                    path,
                    environ,
                    file_attr,
                    is_strm=is_strm,
                    is_media_info=False,
                    local_path=None,
                )

        except Exception as e:
            print(f"Error getting pan children: {e}")

        return children

    def _get_local_children(
        self, dir_: str, environ: dict
    ) -> "Dict[str, HybridFileResource]":
        """
        获取本地媒体信息文件
        """
        children: "Dict[str, HybridFileResource]" = {}

        if not self.local_mapping_path or not os.path.exists(self.local_mapping_path):
            return children

        try:
            for item in os.listdir(self.local_mapping_path):
                item_path = os.path.join(self.local_mapping_path, item)
                if os.path.isfile(item_path):
                    # 检查是否是媒体信息文件
                    if self._is_media_info_file(item):
                        name = item
                        path = dir_ + name

                        file_attr = {
                            "id": f"local_{hash(item_path)}",
                            "name": item,
                            "is_dir": False,
                            "mtime": os.path.getmtime(item_path),
                            "size": os.path.getsize(item_path),
                        }

                        children[name] = HybridFileResource(
                            path,
                            environ,
                            file_attr,
                            is_strm=False,
                            is_media_info=True,
                            local_path=item_path,
                        )

        except Exception as e:
            print(f"Error getting local children: {e}")

        return children

    def _should_be_strm(self, filename: str, filesize: Optional[int] = None) -> bool:
        """
        判断文件是否应该转换为STRM
        """
        # 检查文件扩展名
        user_rmt_mediaext = getattr(configer, "user_rmt_mediaext", "")
        if user_rmt_mediaext:
            media_extensions = {
                f".{ext.strip()}"
                for ext in user_rmt_mediaext.replace("，", ",").split(",")
            }

            if not any(filename.lower().endswith(ext) for ext in media_extensions):
                return False

        # 检查文件大小
        min_file_size = getattr(configer, "full_sync_min_file_size", None)
        if filesize and min_file_size:
            if filesize < min_file_size:
                return False

        # 检查黑名单
        _, should_generate = StrmGenerater.should_generate_strm(
            filename, "full", filesize
        )

        return should_generate

    def _is_media_info_file(self, filename: str) -> bool:
        """
        判断是否是媒体信息文件
        """
        user_download_mediaext = getattr(configer, "user_download_mediaext", "")
        if not user_download_mediaext:
            return False

        media_info_extensions = {
            f".{ext.strip()}"
            for ext in user_download_mediaext.replace("，", ",").split(",")
        }

        return any(filename.lower().endswith(ext) for ext in media_info_extensions)

    def _get_local_mapping_path(self, webdav_path: str) -> Optional[str]:
        """
        获取本地映射路径
        """
        if (
            not hasattr(configer, "webdav_local_mapping_path")
            or not configer.webdav_local_mapping_path
        ):
            return None

        # 将webdav路径转换为本地路径
        relative_path = webdav_path.strip("/")
        if relative_path.startswith("<share/"):
            relative_path = relative_path[7:]  # 移除 '<share/' 前缀

        return os.path.join(configer.webdav_local_mapping_path, relative_path)

    def _get_media_info_path(
        self, webdav_path: str, original_filename: str
    ) -> Optional[str]:
        """
        获取媒体信息文件路径
        """
        local_mapping = self._get_local_mapping_path(webdav_path)
        if not local_mapping:
            return None

        # 查找对应的媒体信息文件
        base_name = splitext(original_filename)[0]
        user_download_mediaext = getattr(configer, "user_download_mediaext", "")
        if user_download_mediaext:
            for ext in user_download_mediaext.replace("，", ",").split(","):
                ext = ext.strip()
                media_info_file = os.path.join(local_mapping, f"{base_name}.{ext}")
                if os.path.exists(media_info_file):
                    return media_info_file

        return None

    def get_member(
        self, /, name: str
    ) -> "Union[HybridFileResource, HybridFolderResource]":
        """
        获取指定成员
        """
        if attr := self.children.get(name):
            return attr
        raise DAVError(404, self.path + "/" + name)

    def get_member_list(
        self, /
    ) -> "list[Union[HybridFileResource, HybridFolderResource]]":
        """
        获取成员列表
        """
        return list(self.children.values())

    def get_member_names(self, /) -> list[str]:
        """
        获取成员名称列表
        """
        return list(self.children)

    def get_property_value(self, /, name: str):
        """
        获取属性值
        """
        if name == "{DAV:}getcontentlength":
            return 0
        elif name == "{DAV:}iscollection":
            return True
        return super().get_property_value(name)

    def create_collection(self, /, name: str) -> "HybridFolderResource":
        """
        创建文件夹
        """
        if not self.local_mapping_path:
            raise DAVError(403, "Cannot create collection: no local mapping path")

        # 创建本地文件夹
        new_folder_path = os.path.join(self.local_mapping_path, name)
        os.makedirs(new_folder_path, exist_ok=True)

        # 创建WebDAV资源
        folder_attr = {
            "id": f"local_folder_{hash(new_folder_path)}",
            "name": name,
            "is_dir": True,
            "mtime": time.time(),
            "size": 0,
        }

        return HybridFolderResource(
            self.path + "/" + name, self.environ, folder_attr, new_folder_path
        )

    def create_empty_resource(self, /, name: str) -> HybridFileResource:
        """
        创建空文件
        """
        if not self.local_mapping_path:
            raise DAVError(403, "Cannot create file: no local mapping path")

        # 创建本地文件
        new_file_path = os.path.join(self.local_mapping_path, name)
        with open(new_file_path, "w", encoding="utf-8") as f:
            f.write("")

        file_attr = {
            "id": f"local_file_{hash(new_file_path)}",
            "name": name,
            "is_dir": False,
            "mtime": time.time(),
            "size": 0,
        }

        return HybridFileResource(
            self.path + "/" + name,
            self.environ,
            file_attr,
            is_strm=False,
            is_media_info=self._is_media_info_file(name),
            local_path=new_file_path,
        )

    def delete(self, /, name: str) -> None:
        """
        删除文件或文件夹
        """
        if not self.local_mapping_path:
            raise DAVError(403, "Cannot delete: no local mapping path")

        item_path = os.path.join(self.local_mapping_path, name)
        if os.path.exists(item_path):
            if os.path.isdir(item_path):
                os.rmdir(item_path)
            else:
                os.remove(item_path)


class HybridP115FileSystemProvider(DAVProvider):
    """
    混合P115文件系统提供者
    """

    def __init__(self, local_mapping_path: str):
        super().__init__()
        self.local_mapping_path = local_mapping_path
        # 确保本地映射目录存在
        os.makedirs(local_mapping_path, exist_ok=True)

    def get_resource_inst(
        self,
        /,
        path: str,
        environ: dict,
    ) -> "Union[HybridFolderResource, HybridFileResource]":
        """
        获取资源实例
        """
        path = "/" + path.strip("/")

        # 处理根目录
        if path == "/":
            root_attr = {"id": 0, "name": "root", "is_dir": True, "mtime": 0, "size": 0}
            return HybridFolderResource(
                "/", environ, root_attr, self.local_mapping_path
            )

        # 处理其他路径
        dir_, name = splitpath(path)

        # 获取父目录
        if dir_ == "/":
            parent = self.get_resource_inst("/", environ)
        else:
            parent = self.get_resource_inst(dir_ + "/", environ)

        if not isinstance(parent, HybridFolderResource):
            raise DAVError(404, path)

        # 获取子项
        try:
            return parent.get_member(name)
        except DAVError as exc:
            raise DAVError(404, path) from exc

    def is_readonly(self, /) -> bool:
        """
        检查是否只读
        """
        return False


def create_hybrid_webdav_app(local_mapping_path: str) -> WsgiDAVApp:
    """
    创建混合WebDAV应用
    """
    config = {
        "provider_mapping": {
            "/": HybridP115FileSystemProvider(local_mapping_path),
        },
        "simple_dc": {"user_mapping": {"*": True}},
        "verbose": 1,
    }

    return WsgiDAVApp(config)
