import json
import platform
from typing import Dict, Any, Optional, List
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.log import logger
from app.core.config import settings
from app.utils.system import SystemUtils
from app.db.systemconfig_oper import SystemConfigOper


class BaseConfig(BaseModel):
    """
    基础配置
    """

    class Config:
        extra = "ignore"

    # 插件名称
    PLUSIN_NAME: str = "P115StrmHelper"
    # 是否开启数据库WAL模式
    DB_WAL_ENABLE: bool = True
    # 插件配置目录
    PLUGIN_CONFIG_PATH: str = str(settings.PLUGIN_DATA_PATH / PLUSIN_NAME.lower())
    # 插件数据库目录
    PLUGIN_DB_PATH: str = str(Path(PLUGIN_CONFIG_PATH) / "p115strmhelper_file.db")
    # 插件数据库表目录
    PLUGIN_DATABASE_PATH: str = str(
        settings.ROOT_PATH / "app/plugins" / PLUSIN_NAME.lower() / "database"
    )
    # 插件临时目录
    PLUGIN_TEMP_PATH: str = str(Path(PLUGIN_CONFIG_PATH) / "temp")
    # 插件缓存目录
    PLUGIN_CACHE_PATH: str = str(Path(PLUGIN_CONFIG_PATH) / "cache")

    # 插件总开关
    enabled: bool = False
    # 通知开关
    notify: bool = False
    # 生成 STRM URL 格式
    strm_url_format: str = "pickcode"
    # 302 跳转方式
    link_redirect_mode: str = "cookie"
    # 115 Cookie
    cookies: Optional[str] = None
    # 115 安全码
    password: Optional[str] = None
    # MoviePilot 地址
    moviepilot_address: Optional[str] = None
    # 可识别媒体后缀
    user_rmt_mediaext: str = (
        "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v"
    )
    # 可识别下载后缀
    user_download_mediaext: str = "srt,ssa,ass"

    # 整理事件监控开关
    transfer_monitor_enabled: bool = False
    # 刮削 STRM 开关
    transfer_monitor_scrape_metadata_enabled: bool = False
    # 刮削排除目录
    transfer_monitor_scrape_metadata_exclude_paths: Optional[str] = None
    # 监控目录
    transfer_monitor_paths: Optional[str] = None
    # MP-媒体库 目录转换
    transfer_mp_mediaserver_paths: Optional[str] = None
    # 刷新媒体服务器
    transfer_monitor_mediaservers: Optional[List[str]] = None
    # 刷新媒体服务器开关
    transfer_monitor_media_server_refresh_enabled: bool = False

    # 全量同步覆盖模式
    full_sync_overwrite_mode: str = "never"
    # 清理无效 STRM 文件
    full_sync_remove_unless_strm: bool = False
    # 定期全量同步开关
    timing_full_sync_strm: bool = False
    # 下载媒体信息文件开关
    full_sync_auto_download_mediainfo_enabled: bool = False
    # 定期全量同步周期
    cron_full_sync_strm: str = "0 */7 * * *"
    # 全量同步路径
    full_sync_strm_paths: Optional[str] = None

    # 增量同步开关
    increment_sync_strm_enabled: bool = False
    # 下载媒体信息文件开关
    increment_sync_auto_download_mediainfo_enabled: bool = False
    # 运行周期
    increment_sync_cron: str = "0 * * * *"
    # 增量同步目录
    increment_sync_strm_paths: Optional[str] = None
    # MP-媒体库 目录转换
    increment_sync_mp_mediaserver_paths: Optional[str] = None
    # 刮削 STRM 开关
    increment_sync_scrape_metadata_enabled: bool = False
    # 刮削排除目录
    increment_sync_scrape_metadata_exclude_paths: Optional[str] = None
    # 刷新媒体服务器开关
    increment_sync_media_server_refresh_enabled: bool = False
    # 刷新媒体服务器
    increment_sync_mediaservers: Optional[List[str]] = None

    # 监控生活事件开关
    monitor_life_enabled: bool = False
    # 下载媒体信息文件开关
    monitor_life_auto_download_mediainfo_enabled: bool = False
    # 生活事件监控目录
    monitor_life_paths: Optional[str] = None
    # MP-媒体库 目录转换
    monitor_life_mp_mediaserver_paths: Optional[str] = None
    # 刷新媒体服务器开关
    monitor_life_media_server_refresh_enabled: bool = False
    # 刷新媒体服务器
    monitor_life_mediaservers: Optional[List[str]] = None
    # 监控事件类型
    monitor_life_event_modes: Optional[List[str]] = None
    # 刮削 STRM 开关
    monitor_life_scrape_metadata_enabled: bool = False
    # 刮削排除目录
    monitor_life_scrape_metadata_exclude_paths: Optional[str] = None

    # 分享生成 STRM 运行开关
    share_strm_auto_download_mediainfo_enabled: bool = False
    # 分享码
    user_share_code: Optional[str] = None
    # 分享密码
    user_receive_code: Optional[str] = None
    # 分享链接
    user_share_link: Optional[str] = None
    # 分享目录
    user_share_pan_path: Optional[str] = None
    # 本地 STRM 目录
    user_share_local_path: Optional[str] = None

    # 清理回收站开关
    clear_recyclebin_enabled: bool = False
    # 清理 最近接收 目录开关
    clear_receive_path_enabled: bool = False
    # 清理周期
    cron_clear: str = "0 */7 * * *"

    # 网盘整理开关
    pan_transfer_enabled: bool = False
    # 网盘整理目录
    pan_transfer_paths: Optional[str] = None

    # 监控目录上传开关
    directory_upload_enabled: bool = False
    # 监控目录模式
    directory_upload_mode: str = "compatibility"
    # 可上传文件后缀
    directory_upload_uploadext: str = (
        "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v"
    )
    # 可本地操作文件后缀
    directory_upload_copyext: str = "srt,ssa,ass"
    # 监控目录信息
    directory_upload_path: Optional[List[Dict]] = None

    # CloudSaver 地址
    cloudsaver_url: Optional[str] = None
    # CloudSaver 用户名
    cloudsaver_username: Optional[str] = None
    # CloudSaver 密码
    cloudsaver_password: Optional[str] = None


class ConfigManager:
    """
    配置操作器
    """

    def __init__(self):
        self._configs = {}

    def fix_config(self, config_dict: Dict[str, Any]) -> Dict:
        """
        修复非法值
        """
        fixed_dict = config_dict
        for field_name, field in BaseConfig.__fields__.items():
            if field.type_ is bool and field_name in fixed_dict:
                value = fixed_dict[field_name]
                if not isinstance(value, bool):
                    default_value = field.default
                    logger.warning(
                        f"【配置管理器】配置项 {field_name} 的值 {value} 不是布尔类型，已替换为默认值 {default_value}"
                    )
                    fixed_dict[field_name] = default_value
            elif (
                field.type_ is str
                and field_name in fixed_dict
                and field_name
                in [
                    "PLUGIN_CONFIG_PATH",
                    "PLUGIN_TEMP_PATH",
                    "PLUGIN_DB_PATH",
                    "PLUGIN_DATABASE_PATH",
                    "PLUGIN_CACHE_PATH",
                ]
            ):
                value = fixed_dict[field_name]
                if not isinstance(value, str):
                    default_value = field.default
                    logger.warning(
                        f"【配置管理器】路径 {field_name} 的值 {value} 不是字符串类型，已替换为默认值 {default_value}"
                    )
                    fixed_dict[field_name] = default_value
        return fixed_dict

    def load_from_dict(self, config_dict: Dict[str, Any]) -> bool:
        """
        从字典加载配置
        """
        try:
            fixed_dict = self.fix_config(config_dict.copy())
            validated = BaseConfig(**fixed_dict)
            self._configs = validated.dict()
            return True
        except ValidationError as e:
            logger.error(f"【配置管理器】配置验证失败: {e}")
            return False

    def load_from_json(self, json_str: str) -> bool:
        """
        从JSON字符串加载配置
        """
        try:
            return self.load_from_dict(json.loads(json_str))
        except json.JSONDecodeError:
            logger.error("【配置管理器】无效的JSON格式")
            return False

    def get_config(self, key: str) -> Optional[Any]:
        """
        获取单个配置值
        """
        if key in [
            "PLUGIN_CONFIG_PATH",
            "PLUGIN_TEMP_PATH",
            "PLUGIN_DB_PATH",
            "PLUGIN_DATABASE_PATH",
            "PLUGIN_CACHE_PATH",
        ]:
            return Path(self._configs.get(key))
        return self._configs.get(key)

    def get_all_configs(self) -> Dict[str, Any]:
        """
        获取所有配置的副本
        """
        self._configs = self.fix_config(self._configs)
        return self._configs.copy()

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        更新部分配置
        """
        try:
            # 合并现有配置和更新
            self._configs = self.fix_config(self._configs)
            current = BaseConfig(**self._configs)
            updated = current.copy(update=updates)
            self._configs.update(updated.dict())
            return True
        except ValidationError as e:
            logger.error(f"【配置管理器】配置更新失败: {e.json()}")
            return False

    def update_plugin_config(self):
        """
        更新插件配置到数据库
        """
        systemconfig = SystemConfigOper()
        plugin_id = self._configs.get("PLUSIN_NAME")
        return systemconfig.set(f"plugin.{plugin_id}", self._configs)

    def get_user_agent(self, utype: int = -1):
        """
        获取指定 USER_AGENT
        """
        user_agents = {
            1: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            2: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            3: settings.USER_AGENT,
            4: "Mozilla/5.0 (Linux; Android 11; Redmi Note 8 Pro Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/89.0.4389.72 MQQBrowser/6.2 TBS/045913 Mobile Safari/537.36 V1_AND_SQ_8.8.68_2538_YYB_D A_8086800 QQ/8.8.68.7265 NetType/WIFI WebP/0.3.0 Pixel/1080 StatusBarHeight/76 SimpleUISwitch/1 QQTheme/2971 InMagicWin/0 StudyMode/0 CurrentMode/1 CurrentFontScale/1.0 GlobalDensityScale/0.9818182 AppId/537112567 Edg/98.0.4758.102",
        }
        if utype in user_agents:
            return user_agents[utype]
        return (
            f"{self._configs.get('PLUSIN_NAME')}/1.0.0 "
            f"({platform.system()} {platform.release()}; "
            f"{SystemUtils.cpu_arch() if hasattr(SystemUtils, 'cpu_arch') and callable(SystemUtils.cpu_arch) else 'UnknownArch'})"
        )


configer = ConfigManager()
