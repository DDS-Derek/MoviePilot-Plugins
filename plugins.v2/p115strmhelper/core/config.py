from platform import system, release
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

from orjson import loads, JSONDecodeError
from pydantic import BaseModel, ValidationError, Field

from app.log import logger
from app.core.config import settings
from app.utils.system import SystemUtils
from app.db.systemconfig_oper import SystemConfigOper
from app.db.plugindata_oper import PluginDataOper

from ..version import VERSION
from ..core.aliyunpan import AliyunPanLogin
from ..utils.machineid import MachineID


class ConfigManager(BaseModel):
    """
    插件配置管理器
    """

    @staticmethod
    def _get_default_plugin_config_path() -> Path:
        """
        返回默认的插件配置目录路径
        """
        return settings.PLUGIN_DATA_PATH / "p115strmhelper"

    @staticmethod
    def _get_default_plugin_db_path() -> Path:
        """
        返回默认的插件数据库文件路径
        """
        return (
            ConfigManager._get_default_plugin_config_path() / "p115strmhelper_file.db"
        )

    @staticmethod
    def _get_default_plugin_database_script_location() -> Path:
        """
        返回默认的插件数据库结构目录路径
        """
        return settings.ROOT_PATH / "app" / "plugins" / "p115strmhelper" / "database"

    @staticmethod
    def _get_default_plugin_temp_path() -> Path:
        """
        返回默认的插件临时目录路径
        """
        return ConfigManager._get_default_plugin_config_path() / "temp"

    class Config:
        extra = "ignore"
        arbitrary_types_allowed = True
        validate_assignment = True
        json_encoders = {Path: str}

    # 插件名称
    PLUSIN_NAME: str = Field("P115StrmHelper", min_length=1)
    # 是否开启数据库WAL模式
    DB_WAL_ENABLE: bool = True
    # 插件配置目录
    PLUGIN_CONFIG_PATH: Path = Field(default_factory=_get_default_plugin_config_path)
    # 插件数据库目录
    PLUGIN_DB_PATH: Path = Field(default_factory=_get_default_plugin_db_path)
    # 插件数据库表目录
    PLUGIN_DATABASE_SCRIPT_LOCATION: Path = Field(
        default_factory=_get_default_plugin_database_script_location
    )
    PLUGIN_DATABASE_VERSION_LOCATIONS: List[str] = [
        str(_get_default_plugin_config_path() / "database/versions")
    ]
    # 插件临时目录
    PLUGIN_TEMP_PATH: Path = Field(default_factory=_get_default_plugin_temp_path)

    # 插件语言
    language: str = Field("zh_CN", min_length=1)

    # 插件总开关
    enabled: bool = False
    # 通知开关
    notify: bool = False
    # 生成 STRM URL 格式
    strm_url_format: str = Field("pickcode", min_length=1)
    # 302 跳转方式
    link_redirect_mode: str = Field("cookie", min_length=1)
    # 115 Cookie
    cookies: Optional[str] = None
    # 阿里云盘 Token
    aliyundrive_token: Optional[str] = None
    # 115 安全码
    password: Optional[str] = None
    # MoviePilot 地址
    moviepilot_address: Optional[str] = Field(None, min_length=1)
    # 可识别媒体后缀
    user_rmt_mediaext: str = Field(
        "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
        min_length=1,
    )
    # 可识别下载后缀
    user_download_mediaext: str = Field("srt,ssa,ass", min_length=1)

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
    cron_full_sync_strm: Optional[str] = None
    # 全量生成最小文件大小
    full_sync_min_file_size: Optional[int] = None
    # 全量同步路径
    full_sync_strm_paths: Optional[str] = None
    # 全量生成输出详细日志
    full_sync_strm_log: bool = True
    # 全量同步单次批处理量
    full_sync_batch_num: Union[int, str] = 5_000
    # 全量同步文件处理线程数
    full_sync_process_num: Union[int, str] = 128
    # 全量同步使用的函数
    full_sync_iter_function: str = Field("iter_files_with_path_skim", min_length=1)

    # 增量同步开关
    increment_sync_strm_enabled: bool = False
    # 下载媒体信息文件开关
    increment_sync_auto_download_mediainfo_enabled: bool = False
    # 运行周期
    increment_sync_cron: Optional[str] = None
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
    # 增量生成最小文件大小
    increment_sync_min_file_size: Optional[int] = None

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
    # 同步删除本地STRM时是否删除MP整理记录
    monitor_life_remove_mp_history: bool = False
    # 同上方情况时是否删除源文件
    monitor_life_remove_mp_source: bool = False
    # 生活事件生成最小文件大小
    monitor_life_min_file_size: Optional[int] = None
    # 生活事件启动拉取模式
    monitor_life_first_pull_mode: str = Field("latest", min_length=1)

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
    # 分享生成最小文件大小
    share_strm_min_file_size: Optional[int] = None

    # 清理回收站开关
    clear_recyclebin_enabled: bool = False
    # 清理 最近接收 目录开关
    clear_receive_path_enabled: bool = False
    # 清理周期
    cron_clear: Optional[str] = None

    # 网盘整理开关
    pan_transfer_enabled: bool = False
    # 网盘整理目录
    pan_transfer_paths: Optional[str] = None
    # 网盘整理未识别目录
    pan_transfer_unrecognized_path: Optional[str] = None

    # 监控目录上传开关
    directory_upload_enabled: bool = False
    # 监控目录模式
    directory_upload_mode: str = Field("compatibility", min_length=1)
    # 可上传文件后缀
    directory_upload_uploadext: str = Field(
        "mp4,mkv,ts,iso,rmvb,avi,mov,mpeg,mpg,wmv,3gp,asf,m4v,flv,m2ts,tp,f4v",
        min_length=1,
    )
    # 可本地操作文件后缀
    directory_upload_copyext: str = Field("srt,ssa,ass", min_length=1)
    # 监控目录信息
    directory_upload_path: Optional[List[Dict]] = None

    # TG 搜索频道
    tg_search_channels: Optional[List[Dict]] = None
    # Nullbr APP ID
    nullbr_app_id: Optional[str] = Field(None, min_length=1)
    # Nullbr API KEY
    nullbr_api_key: Optional[str] = Field(None, min_length=1)

    # 多端播放同一个文件
    same_playback: bool = False

    # 上传错误信息
    error_info_upload: bool = True
    # 115 上传增强
    upload_module_enhancement: bool = False
    # 115 上传秒传失败时跳过上传返回失败
    upload_module_skip_slow_upload: bool = False
    # 115 上传增强休眠等待时间
    upload_module_wait_time: int = 5 * 60
    # 115 上传增强最长等待时间
    upload_module_wait_timeout: int = 60 * 60
    # 115 上传增强跳过等待秒传的文件大小阈值
    upload_module_skip_upload_wait_size: Optional[int] = None
    # 115 上传增强强制等待秒传的文件大小阈值
    upload_module_force_upload_wait_size: Optional[int] = None
    # 上传分享链接
    upload_share_info: bool = True
    # 上传离线下载链接
    upload_offline_info: bool = True
    # 115 整理增强
    transfer_module_enhancement: bool = False

    # 高级配置，STRM URL 自定义配置
    strm_url_mode_custom: Optional[str] = None
    # STRM 文件生成黑名单
    strm_generate_blacklist: Optional[List] = None
    # 媒体信息文件下载白名单
    mediainfo_download_whitelist: Optional[List] = None
    # 媒体信息文件下载黑名单
    mediainfo_download_blacklist: Optional[List] = None

    # WebDAV 配置
    webdav_enabled: bool = False
    webdav_port: int = 8080
    webdav_host: str = "0.0.0.0"
    webdav_local_mapping_path: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None

    @property
    def PLUGIN_ALIGO_PATH(self) -> Path:
        """
        返回 aligo 配置的动态路径
        """
        return self.PLUGIN_CONFIG_PATH / "aligo"

    @property
    def MACHINE_ID(self) -> str:
        """
        获取或生成机器ID
        """
        return MachineID.get_or_generate_machine_id(
            self.PLUGIN_CONFIG_PATH / "machine_id.txt"
        )

    @property
    def USER_AGENT(self) -> str:
        """
        全局用户代理字符串
        """
        return self.get_user_agent()

    def _update_aliyun_token(self):
        """
        从文件动态获取最新的阿里云盘Token
        """
        token = AliyunPanLogin.get_token(self.PLUGIN_ALIGO_PATH / "aligo.json")
        if token:
            self.aliyundrive_token = token

    def load_from_dict(self, config_dict: Dict[str, Any]) -> bool:
        """
        从字典加载配置
        """
        try:
            for key, value in config_dict.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            self._update_aliyun_token()
            return True
        except ValidationError as e:
            logger.error(f"【配置管理器】配置验证失败: {e}")
            return False

    def load_from_json(self, json_str: str) -> bool:
        """
        从JSON字符串加载配置
        """
        try:
            return self.load_from_dict(loads(json_str))
        except JSONDecodeError:
            logger.error("【配置管理器】无效的JSON格式")
            return False

    def get_config(self, key: str) -> Optional[Any]:
        """
        获取单个配置值
        """
        if key in ["PLUGIN_ALIGO_PATH", "MACHINE_ID"]:
            return getattr(self, key)
        if key == "aliyundrive_token":
            self._update_aliyun_token()
        return getattr(self, key, None)

    def get_all_configs(self) -> Dict[str, Any]:
        """
        获取所有配置
        """
        self._update_aliyun_token()
        json_string = self.json()
        serializable_dict = loads(json_string)
        return serializable_dict

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        更新一个或多个配置项
        """
        try:
            for key, value in updates.items():
                if hasattr(self, key):
                    setattr(self, key, value)

            if "aliyundrive_token" in updates:
                if not updates.get("aliyundrive_token"):
                    (self.PLUGIN_ALIGO_PATH / "aligo.json").unlink(missing_ok=True)
            else:
                self._update_aliyun_token()
            return True
        except ValidationError as e:
            logger.error(f"【配置管理器】配置更新失败: {e.json()}")
            return False

    def update_plugin_config(self) -> Optional[bool]:
        """
        将当前配置状态保存到数据库
        """
        systemconfig = SystemConfigOper()
        plugin_id = self.PLUSIN_NAME
        json_string = self.json()
        serializable_dict = loads(json_string)
        return systemconfig.set(f"plugin.{plugin_id}", serializable_dict)

    def get_user_agent(self, utype: int = -1) -> str:
        """
        根据类型获取指定的User-Agent
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
            f"{self.PLUSIN_NAME}/{VERSION} "
            f"({system()} {release()}; "
            f"{SystemUtils.cpu_arch() if hasattr(SystemUtils, 'cpu_arch') and callable(SystemUtils.cpu_arch) else 'UnknownArch'})"
        )

    def save_plugin_data(self, key: str, value: Any):
        """
        保存插件数据
        :param key: 数据key
        :param value: 数据值
        """
        plugindata = PluginDataOper()
        plugindata.save(self.PLUSIN_NAME, key, value)

    def get_plugin_data(self, key: Optional[str] = None) -> Any:
        """
        获取插件数据
        :param key: 数据key
        """
        plugindata = PluginDataOper()
        return plugindata.get_data(self.PLUSIN_NAME, key)

    def del_plugin_data(self, key: str) -> Any:
        """
        删除插件数据
        :param key: 数据key
        """
        plugindata = PluginDataOper()
        return plugindata.del_data(self.PLUSIN_NAME, key)


configer = ConfigManager()
