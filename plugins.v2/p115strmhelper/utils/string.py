import re

from ..core.i18n import i18n


class StringUtils:
    """
    类型转换辅助类
    """

    @staticmethod
    def format_size(size: float, precision: int = 2) -> str:
        """
        字节数转换
        """
        if not isinstance(size, (int, float)) or size < 0:
            return "N/A"
        suffixes = ["B", "KB", "MB", "GB", "TB"]
        suffix_index = 0
        while size >= 1024 and suffix_index < 4:
            suffix_index += 1
            size /= 1024.0
        return f"{size:.{precision}f} {suffixes[suffix_index]}"

    @staticmethod
    def to_emoji_number(n: int) -> str:
        """
        将一个整数转换为对应的带圈数字 Emoji 字符串 (例如 ①, ②, ⑩)。
        """
        if not isinstance(n, int):
            return "❓"
        if n == 10:
            return "⑩"
        emoji_map = {
            "0": "⓪",
            "1": "①",
            "2": "②",
            "3": "③",
            "4": "④",
            "5": "⑤",
            "6": "⑥",
            "7": "⑦",
            "8": "⑧",
            "9": "⑨",
        }
        return "".join(emoji_map.get(digit, digit) for digit in str(n))

    @staticmethod
    def replace_markdown_with_space(text: str) -> str:
        """
        将字符串中所有常见的 Markdown 特殊字符替换为空格

        :param text: 需要处理的带md特殊字符的文案
        """
        if not isinstance(text, str):
            return ""

        # 需要处理的字符串，必须字符：` * [ ]
        md_chars_list = ["*", "[", "]", "`", "."]

        # 修剪特殊字符
        for char in md_chars_list:
            if char == ".":
                text = text.replace(char, "·")
            else:
                text = text.replace(char, " ")

        # 整合连续空格
        normalized_text = re.sub(r"\s+", " ", text)

        return normalized_text.strip()

    @staticmethod
    def media_type_i18n(media_type: str) -> str:
        """
        媒体类型
        """
        if media_type == "movie":
            return i18n.translate("media_type_movie")
        elif media_type == "tv":
            return i18n.translate("media_type_tv")
        return i18n.translate("media_type_collection")
