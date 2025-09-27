from pathlib import Path
from typing import Optional
from urllib.parse import quote

from app.core.config import settings

from ahocorasick import Automaton

from ..core.config import configer


class StrmUrlGetter:
    """
    获取 Strm URL
    """

    def __init__(self):
        self.strmurlmoderesolver = None
        if configer.strm_url_mode_custom:
            self.strmurlmoderesolver = StrmUrlModeResolver(
                configer.strm_url_mode_custom, configer.strm_url_format
            )
        self.strm_url_encode = configer.strm_url_encode

    def get_strm_url(self, pickcode: str, file_name: str) -> str:
        """
        获取普通 STRM URL
        """
        strm_url_format = None

        if self.strmurlmoderesolver:
            strm_url_format = self.strmurlmoderesolver.get_mode(file_name)

        if strm_url_format not in {"pickname", "pickcode"}:
            strm_url_format = configer.strm_url_format

        strm_url = f"{configer.moviepilot_address.rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&pickcode={pickcode}"
        if strm_url_format == "pickname":
            if self.strm_url_encode:
                file_name = quote(file_name)
            strm_url += f"&file_name={file_name}"

        return strm_url

    def get_share_strm_url(
        self, share_code: str, receive_code: str, file_id: str, file_name: str
    ) -> str:
        """
        获取分享 STRM URL
        """
        strm_url_format = None

        if self.strmurlmoderesolver:
            strm_url_format = self.strmurlmoderesolver.get_mode(file_name)

        if strm_url_format not in {"pickname", "pickcode"}:
            strm_url_format = configer.strm_url_format

        strm_url = f"{configer.moviepilot_address.rstrip('/')}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={settings.API_TOKEN}&share_code={share_code}&receive_code={receive_code}&id={file_id}"
        if strm_url_format == "pickname":
            strm_url += f"&file_name={file_name}"

        return strm_url


class StrmUrlModeResolver:
    """
    STRM文件URL格式解析器
    """

    def __init__(self, config_str: str, default_mode: str = "pickcode"):
        self.default_mode = default_mode
        self.rules = self._parse_config(config_str)

    @staticmethod
    def _parse_config(config_str: str) -> dict:
        """
        解析配置字符串并将其转换为一个易于查询的字典

        Args:
            config_str (str): 待解析的规则字符串

        Returns:
            dict: 一个从后缀名到模式的映射字典
        """
        rules_map = {}
        for rule in config_str.strip().split("\n"):
            if "=>" not in rule:
                continue

            extensions_part, mode = rule.split("=>")
            extensions = [ext.strip().lower() for ext in extensions_part.split(",")]
            mode = mode.strip()

            for ext in extensions:
                if not ext.startswith("."):
                    ext = "." + ext
                rules_map[ext] = mode
        return rules_map

    def get_mode(self, file: str) -> str:
        """
        根据输入的文件名后缀获取对应的模式。

        Args:
            file (str): 包含后缀的文件

        Returns:
            str: 匹配到的模式字符串，如果没有匹配则返回默认模式
        """
        extension = Path(file).suffix.lower()

        return self.rules.get(extension, self.default_mode)


class StrmGenerater:
    """
    STRM 文件生成工具类
    """

    @staticmethod
    def should_generate_strm(
        filename: str,
        mode: str,
        filesize: Optional[int] = None,
        blacklist_automaton: Optional[Automaton] = None,
    ) -> tuple[str, bool]:
        """
        判断文件是否能生成总规则
        """
        # 1. 判断是否在黑名单
        if blacklist_automaton:
            blacklist_msg, blacklist_status = StrmGenerater.not_blacklist_key_automaton(
                filename, blacklist_automaton
            )
        else:
            blacklist_msg, blacklist_status = StrmGenerater.not_blacklist_key(filename)
        if not blacklist_status:
            return blacklist_msg, blacklist_status

        # 2. 判断大小是否低于最低限制
        minsize_msg, minsize_status = StrmGenerater.not_min_limit(mode, filesize)
        if not minsize_status:
            return minsize_msg, minsize_status

        return "", True

    @staticmethod
    def not_blacklist_key_automaton(
        filename, blacklist_automaton: Automaton
    ) -> tuple[str, bool]:
        """
        使用 Aho-Corasick 自动机判断文件名是否包含黑名单中的任何关键词
        """
        if not blacklist_automaton:
            return "", True
        lower_filename = filename.lower()
        try:
            _, (original_keyword, _) = next(blacklist_automaton.iter(lower_filename))
            return f"匹配到黑名单关键词 {original_keyword}", False
        except StopIteration:
            return "", True

    @staticmethod
    def not_blacklist_key(filename) -> tuple[str, bool]:
        """
        判断文件名是否包含黑名单中的任何关键词
        """
        blacklist = configer.strm_generate_blacklist

        if not blacklist:
            return "", True
        lower_filename = filename.lower()
        for keyword in blacklist:  # pylint: disable=E1133
            if keyword.lower() in lower_filename:
                return f"匹配到黑名单关键词 {keyword}", False
        return "", True

    @staticmethod
    def not_min_limit(mode: str, filesize: Optional[int] = None) -> tuple[str, bool]:
        """
        判断文件大小是否低于最低限制
        """
        min_size = None
        if mode == "full":
            min_size = configer.full_sync_min_file_size
        elif mode == "life":
            min_size = configer.monitor_life_min_file_size
        elif mode == "increment":
            min_size = configer.increment_sync_min_file_size
        elif mode == "share":
            min_size = configer.share_strm_min_file_size

        if not min_size or min_size == 0:
            return "", True

        if not filesize:
            return "", True

        if filesize < min_size:
            return "小于最小文件大小", False

        return "", True
