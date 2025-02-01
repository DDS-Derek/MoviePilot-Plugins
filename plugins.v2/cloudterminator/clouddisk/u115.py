from typing import Optional
from p115 import P115Client

from app.log import logger


class __U115Manager:
    """
    115 网盘管理器
    """

    def connect(self, cookie: Optional[dict | str]) -> Optional[P115Client]:
        """
        连接 115 网盘
        """
        try:
            if not cookie:
                raise ValueError("cookie is required")
            ssoent = self.get_ssoent(cookie=cookie)
            app = self.get_client_drive_label(ssoent=ssoent, key='app')
            p115client = P115Client(cookie, check_for_relogin=True, ensure_cookies=True, app=app)
            return p115client
        except Exception as e:
            logger.error(f"115 网盘连接失败: {e}")
            return None

    @staticmethod
    def disconnect(p115client: Optional[P115Client]) -> bool:
        """
        断开 115 网盘连接
        """
        if p115client:
            p115client.logout()
        return True

    @staticmethod
    def get_ssoent(cookie: Optional[str]) -> Optional[str]:
        """
        从cookie中获取ssoent
        """
        if not cookie:
            raise ValueError("cookie is required")
        ssoent = None
        # 将cookie拆分成各个部分，并去除首尾换行符空格符
        cookie_parts = [part.strip() for part in cookie.split(';')]
        for part in cookie_parts:
            if 'UID=' in part:
                uid_value = part.split('=')[1]
                ssoent = uid_value.split('_')[1]
        if not ssoent:
            raise ValueError("ssoent is required")
        return ssoent

    def get_client_drive_label(self, ssoent: Optional[str], key: Optional[str] = None) -> Optional[str | dict]:
        """
        获取客户端驱动标签
        """
        if not ssoent:
            raise ValueError("ssoent is required")

        for k, v in self.ssoent_map.items():
            if ssoent == k:
                if key in v.keys():
                    return v.get(key)
                else:
                    return v
        return None

    @property
    def ssoent_map(self) -> dict:
        """
        设备字典

        设备列表如下:

        +-------+----------+------------+-------------------------+
        | No.   | ssoent   | app        | description             |
        +=======+==========+============+=========================+
        | 01    | A1       | web        | 网页版                  |
        +-------+----------+------------+-------------------------+
        | 02    | A2       | ?          | 未知: android           |
        +-------+----------+------------+-------------------------+
        | 03    | A3       | ?          | 未知: iphone            |
        +-------+----------+------------+-------------------------+
        | 04    | A4       | ?          | 未知: ipad              |
        +-------+----------+------------+-------------------------+
        | 05    | B1       | ?          | 未知: android           |
        +-------+----------+------------+-------------------------+
        | 06    | D1       | ios        | 115生活(iOS端)          |
        +-------+----------+------------+-------------------------+
        | 07    | D2       | ?          | 未知: ios               |
        +-------+----------+------------+-------------------------+
        | 08    | D3       | 115ios     | 115(iOS端)              |
        +-------+----------+------------+-------------------------+
        | 09    | F1       | android    | 115生活(Android端)      |
        +-------+----------+------------+-------------------------+
        | 10    | F2       | ?          | 未知: android           |
        +-------+----------+------------+-------------------------+
        | 11    | F3       | 115android | 115(Android端)          |
        +-------+----------+------------+-------------------------+
        | 12    | H1       | ipad       | 未知: ipad              |
        +-------+----------+------------+-------------------------+
        | 13    | H2       | ?          | 未知: ipad              |
        +-------+----------+------------+-------------------------+
        | 14    | H3       | 115ipad    | 115(iPad端)             |
        +-------+----------+------------+-------------------------+
        | 15    | I1       | tv         | 115网盘(Android电视端)  |
        +-------+----------+------------+-------------------------+
        | 16    | M1       | qandriod   | 115管理(Android端)      |
        +-------+----------+------------+-------------------------+
        | 17    | N1       | qios       | 115管理(iOS端)          |
        +-------+----------+------------+-------------------------+
        | 18    | O1       | ?          | 未知: ipad              |
        +-------+----------+------------+-------------------------+
        | 19    | P1       | windows    | 115生活(Windows端)      |
        +-------+----------+------------+-------------------------+
        | 20    | P2       | mac        | 115生活(macOS端)        |
        +-------+----------+------------+-------------------------+
        | 21    | P3       | linux      | 115生活(Linux端)        |
        +-------+----------+------------+-------------------------+
        | 22    | R1       | wechatmini | 115生活(微信小程序)     |
        +-------+----------+------------+-------------------------+
        | 23    | R2       | alipaymini | 115生活(支付宝小程序)   |
        +-------+----------+------------+-------------------------+
        | 24    | S1       | harmony    | 115(Harmony端)          |
        +-------+----------+------------+-------------------------+
        """
        return {
            'A1': {'app': 'web', 'description': '115网页端'},
            # 'A2': {'app': '', 'description': '未知: 安卓端'},
            # 'A3': {'app': '', 'description': '未知: iPhone端'},
            # 'A4': {'app': '', 'description': '未知: iPad端'},
            # 'B1': {'app': '', 'description': '未知: 安卓端'},
            'D1': {'app': 'ios', 'description': '115生活(iOS端)'},
            # 'D2': {'app': '', 'description': '未知: ios'},
            'D3': {'app': '115ios', 'description': '115(iOS端)'},
            'F1': {'app': 'android', 'description': '115生活(Android端)'},
            # 'F2': {'app': '', 'description': '未知: android'},
            'F3': {'app': '115android', 'description': '115(Android端)'},
            # 'H1': {'app': '', 'description': '未知: ipad'},
            # 'H2': {'app': '', 'description': '未知: ipad'},
            'H3': {'app': '115ipad', 'description': '115(iPad端)'},
            'I1': {'app': 'tv', 'description': '115网盘(Android电视端)'},
            'M1': {'app': 'qandroid', 'description': '115管理(Android端)'},
            'N1': {'app': 'qios', 'description': '115管理(iOS端)'},
            # 'O1': {'app': '', 'description': '115管理(iPda端)'},
            'P1': {'app': 'windows', 'description': '115生活(Windows端)'},
            'P2': {'app': 'mac', 'description': '115生活(macOS端)'},
            'P3': {'app': 'linux', 'description': '115生活(Linux端)'},
            'R1': {'app': 'wechatmini', 'description': '115生活(微信小程序)'},
            'R2': {'app': 'alipaymini', 'description': '115生活(支付宝小程序)'},
            'S1': {'app': 'harmony', 'description': '115(Harmony端)'},

        }


u115_manager = __U115Manager()
