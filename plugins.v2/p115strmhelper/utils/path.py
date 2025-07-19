from pathlib import Path


class PathUtils:
    """
    路径匹配
    """

    @staticmethod
    def has_prefix(full_path, prefix_path):
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

    @staticmethod
    def get_run_transfer_path(paths, transfer_path):
        """
        判断路径是否为整理路径
        """
        transfer_paths = paths.split("\n")
        for path in transfer_paths:
            if not path:
                continue
            if PathUtils.has_prefix(transfer_path, path):
                return True
        return False

    @staticmethod
    def get_scrape_metadata_exclude_path(paths, scrape_path):
        """
        检查目录是否在排除目录内
        """
        exclude_path = paths.split("\n")
        for path in exclude_path:
            if not path:
                continue
            if PathUtils.has_prefix(scrape_path, path):
                return True
        return False

    @staticmethod
    def get_media_path(paths, media_path):
        """
        获取媒体目录路径
        """
        media_paths = paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 1)
            if PathUtils.has_prefix(media_path, parts[1]):
                return True, parts[0], parts[1]
        return False, None, None

    @staticmethod
    def get_p115_strm_path(paths, media_path):
        """
        匹配全量目录，自动生成新的 paths
        """
        media_paths = paths.split("\n")
        for path in media_paths:
            if not path:
                continue
            parts = path.split("#", 1)
            if PathUtils.has_prefix(media_path, parts[1]):
                local_path = Path(parts[0]) / Path(media_path).relative_to(parts[1])
                final_paths = f"{local_path}#{media_path}"
                return True, final_paths
        return False, None
