import re
import time
from copy import deepcopy
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional, Union

from app.chain.storage import StorageChain
from app.core.event import eventmanager, Event
from app.core.metainfo import MetaInfoPath
from app.log import logger
from app.plugins import _PluginBase
from app.chain.media import MediaChain
from app.schemas import TransferInfo, FileItem, RefreshMediaItem
from app.schemas.types import EventType, MessageChannel
from apscheduler.triggers.cron import CronTrigger
from fastapi import Request

from .version import VERSION
from .api import Api
from .service import servicer
from .core.cache import pantransfercacher, lifeeventcacher
from .core.config import configer
from .core.i18n import i18n
from .core.message import post_message
from .db_manager import ct_db_manager
from .db_manager.init import init_db, migration_db, init_migration_scripts
from .db_manager.oper import FileDbHelper
from .patch.u115_open import U115Patcher
from .interactive.framework.callbacks import decode_action, Action
from .interactive.framework.manager import BaseSessionManager
from .interactive.framework.schemas import TSession
from .interactive.handler import ActionHandler
from .interactive.session import Session
from .interactive.views import ViewRenderer
from .helper.strm import FullSyncStrmHelper, TransferStrmHelper
from .helper.webdav import webdav_service
from .utils.path import PathUtils
from .utils.sentry import sentry_manager


# 实例化一个该插件专用的 SessionManager
session_manager = BaseSessionManager(session_class=Session)


@sentry_manager.capture_all_class_exceptions
class P115StrmHelper(_PluginBase):
    # 插件名称
    plugin_name = "115网盘STRM助手"
    # 插件描述
    plugin_desc = "115网盘STRM生成一条龙服务"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Frontend/refs/heads/v2/src/assets/images/misc/u115.png"
    # 插件版本
    plugin_version = VERSION
    # 插件作者
    plugin_author = "DDSRem"
    # 作者主页
    author_url = "https://github.com/DDSRem"
    # 插件配置项ID前缀
    plugin_config_prefix = "p115strmhelper_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 1

    api = None

    @staticmethod
    def logs_oper(oper_name: str):
        """
        数据库操作汇报装饰器
        - 捕获异常并记录日志
        - 5秒内合并多条消息，避免频繁发送通知
        """

        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                level, text = "success", f"{oper_name} 成功"
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"{oper_name} 失败：{str(e)}", exc_info=True)
                    level, text = "error", f"{oper_name} 失败：{str(e)}"
                    return False
                finally:
                    if hasattr(self, "add_message"):
                        self.add_message(title=oper_name, text=text, level=level)

            return wrapper

        return decorator

    def __init__(self, config: dict = None):
        """
        初始化
        """
        super().__init__()

        # 初始化配置项
        configer.load_from_dict(config or {})

        if not Path(configer.PLUGIN_TEMP_PATH).exists():
            Path(configer.PLUGIN_TEMP_PATH).mkdir(
                parents=True, exist_ok=True
            )

        # 初始化数据库
        self.init_database()

        # 实例化处理器和渲染器
        self.action_handler = ActionHandler()
        self.view_renderer = ViewRenderer()

        # 初始化通知语言
        i18n.load_translations()

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        self.api = Api(client=None)

        if config:
            configer.update_config(config)
            configer.update_plugin_config()
            i18n.load_translations()
            sentry_manager.reload_config()

        # 停止现有任务
        self.stop_service()

        if configer.enabled:
            self.init_database()

            if servicer.init_service():
                self.api = Api(client=servicer.client)

            U115Patcher().enable()

            # 目录上传监控服务
            servicer.start_directory_upload()

            servicer.start_monitor_life()

            # 启动WebDAV服务
            if configer.webdav_enabled:
                webdav_service.start()

    @logs_oper("初始化数据库")
    def init_database(self) -> bool:
        """
        初始化数据库
        """
        if not Path(configer.PLUGIN_CONFIG_PATH).exists():
            Path(configer.PLUGIN_CONFIG_PATH).mkdir(
                parents=True, exist_ok=True
            )
        if not ct_db_manager.is_initialized():
            # 初始化数据库会话
            ct_db_manager.init_database(db_path=configer.PLUGIN_DB_PATH)
            # 表单补全
            init_db(
                engine=ct_db_manager.Engine,
            )
            # 初始化 迁移脚本
            if init_migration_scripts():
                # 更新数据库
                migration_db(
                    db_path=configer.PLUGIN_DB_PATH,
                    script_location=configer.PLUGIN_DATABASE_SCRIPT_LOCATION,
                    version_locations=configer.PLUGIN_DATABASE_VERSION_LOCATIONS,
                )
            else:
                raise Exception("初始化迁移脚本失败")
        return True

    def get_state(self) -> bool:
        """
        插件状态
        """
        return configer.enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/p115_full_sync",
                "event": EventType.PluginAction,
                "desc": "全量同步115网盘文件",
                "category": "",
                "data": {"action": "p115_full_sync"},
            },
            {
                "cmd": "/p115_inc_sync",
                "event": EventType.PluginAction,
                "desc": "增量同步115网盘文件",
                "category": "",
                "data": {"action": "p115_inc_sync"},
            },
            {
                "cmd": "/p115_add_share",
                "event": EventType.PluginAction,
                "desc": "转存分享到待整理目录",
                "category": "",
                "data": {"action": "p115_add_share"},
            },
            {
                "cmd": "/ol",
                "event": EventType.PluginAction,
                "desc": "添加离线下载任务",
                "category": "",
                "data": {"action": "p115_add_offline"},
            },
            {
                "cmd": "/p115_strm",
                "event": EventType.PluginAction,
                "desc": "全量生成指定网盘目录STRM",
                "category": "",
                "data": {"action": "p115_strm"},
            },
            {
                "cmd": "/sh",
                "event": EventType.PluginAction,
                "desc": "搜索指定资源",
                "category": "",
                "data": {"action": "p115_search"},
            },
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """
        BASE_URL: {server_url}/api/v1/plugin/P115StrmHelper/redirect_url?apikey={APIKEY}
        0. 查询 pickcode
            url: ${BASE_URL}&pickcode=ecjq9ichcb40lzlvx
        1. 带（任意）名字查询 pickcode
            url: ${BASE_URL}&file_name=Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv&pickcode=ecjq9ichcb40lzlvx
        2. 查询分享文件（如果是你自己的分享，则无须提供密码 receive_code）
            url: ${BASE_URL}&share_code=sw68md23w8m&receive_code=q353&id=2580033742990999218
            url: ${BASE_URL}&share_code=sw68md23w8m&id=2580033742990999218
        3. 用 file_name 查询分享文件（直接以路径作为 file_name，且不要有 id 查询参数。如果是你自己的分享，则无须提供密码 receive_code）
            url: ${BASE_URL}&file_name=Cosmos.S01E01.1080p.AMZN.WEB-DL.DD%2B5.1.H.264-iKA.mkv&share_code=sw68md23w8m&receive_code=q353
            url: ${BASE_URL}&file_name=Cosmos.S01E01.1080p.AMZN.WEB-DL.DD%2B5.1.H.264-iKA.mkv&share_code=sw68md23w8m
        """
        return [
            {
                "path": "/redirect_url",
                "endpoint": self.api.redirect_url,
                "methods": ["GET", "POST", "HEAD"],
                "summary": "302跳转",
                "description": "115网盘302跳转",
            },
            {
                "path": "/add_transfer_share",
                "endpoint": self.api.add_transfer_share,
                "methods": ["GET"],
                "summary": "添加分享转存整理",
            },
            {
                "path": "/user_storage_status",
                "endpoint": self.api.get_user_storage_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取115用户基本信息和空间状态",
            },
            {
                "path": "/get_config",
                "endpoint": self.api.get_config_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取配置",
            },
            {
                "path": "/get_machine_id",
                "endpoint": self.api.get_machine_id_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取 Machine ID",
            },
            {
                "path": "/save_config",
                "endpoint": self._save_config_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置",
            },
            {
                "path": "/get_status",
                "endpoint": self.api.get_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取状态",
            },
            {
                "path": "/full_sync",
                "endpoint": self.api.trigger_full_sync_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行全量同步",
            },
            {
                "path": "/full_sync_db",
                "endpoint": self.api.trigger_full_sync_db_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行全量同步",
            },
            {
                "path": "/share_sync",
                "endpoint": self.api.trigger_share_sync_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "执行分享同步",
            },
            {
                "path": "/browse_dir",
                "endpoint": self.api.browse_dir_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "浏览目录",
            },
            {
                "path": "/get_qrcode",
                "endpoint": self.api.get_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取登录二维码",
            },
            {
                "path": "/check_qrcode",
                "endpoint": self.api.check_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查二维码状态",
            },
            {
                "path": "/get_aliyundrive_qrcode",
                "endpoint": self.api.get_aliyundrive_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取阿里云盘登录二维码",
            },
            {
                "path": "/check_aliyundrive_qrcode",
                "endpoint": self.api.check_aliyundrive_qrcode_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "检查阿里云盘二维码状态",
            },
            {
                "path": "/offline_tasks",
                "endpoint": self.api.offline_tasks_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "离线任务列表",
            },
            {
                "path": "/add_offline_task",
                "endpoint": self.api.add_offline_task_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "添加离线下载任务",
            },
            {
                "path": "/check_feature",
                "endpoint": self.api.check_feature_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "判断是否有权限使用此增强功能",
            },
            {
                "path": "/webdav_status",
                "endpoint": self.api.get_webdav_status_api,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取WebDAV服务状态",
            },
            {
                "path": "/webdav_start",
                "endpoint": self.api.start_webdav_service_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "启动WebDAV服务",
            },
            {
                "path": "/webdav_stop",
                "endpoint": self.api.stop_webdav_service_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "停止WebDAV服务",
            },
            {
                "path": "/webdav_restart",
                "endpoint": self.api.restart_webdav_service_api,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "重启WebDAV服务",
            },
        ]

    def get_service(self) -> List[Dict[str, str | Dict[Any, Any] | Any]] | None:
        """
        注册插件公共服务
        """
        cron_service = [
            {
                "id": "P115StrmHelper_offline_status",
                "name": "监控115网盘离线下载进度",
                "trigger": CronTrigger.from_crontab("*/2 * * * *"),
                "func": servicer.offline_status,
                "kwargs": {},
            }
        ]
        if (
            configer.cron_full_sync_strm
            and configer.timing_full_sync_strm
            and configer.full_sync_strm_paths
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_full_sync_strm_files",
                    "name": "定期全量同步115媒体库",
                    "trigger": CronTrigger.from_crontab(
                        configer.cron_full_sync_strm
                    ),
                    "func": servicer.full_sync_strm_files,
                    "kwargs": {},
                }
            )
        if configer.cron_clear and (
            configer.clear_recyclebin_enabled
            or configer.clear_receive_path_enabled
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_main_cleaner",
                    "name": "定期清理115空间",
                    "trigger": CronTrigger.from_crontab(
                        configer.cron_clear
                    ),
                    "func": servicer.main_cleaner,
                    "kwargs": {},
                }
            )
        if (
            configer.increment_sync_strm_enabled
            and configer.increment_sync_strm_paths
            and configer.increment_sync_cron
        ):
            cron_service.append(
                {
                    "id": "P115StrmHelper_increment_sync_strm",
                    "name": "115网盘定期增量同步",
                    "trigger": CronTrigger.from_crontab(
                        configer.increment_sync_cron
                    ),
                    "func": servicer.increment_sync_strm_files,
                    "kwargs": {},
                }
            )
        if cron_service:
            return cron_service

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """
        返回插件使用的前端渲染模式
        :return: 前端渲染模式，前端文件目录
        """
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """
        为Vue组件模式返回初始配置数据。
        Vue模式下，第一个参数返回None，第二个参数返回初始配置数据。
        """
        return None, self.api.get_config_api()

    def get_page(self) -> Optional[List[dict]]:
        """
        Vue模式不使用Vuetify页面定义
        """
        return None

    @eventmanager.register(EventType.TransferComplete)
    def delete_top_pan_transfer_path(self, event: Event):
        """
        处理网盘整理MP无法删除的顶层目录
        """

        if not configer.pan_transfer_enabled or not configer.pan_transfer_paths:
            return

        if not pantransfercacher.top_delete_pan_transfer_list:
            return

        item = event.event_data
        if not item:
            return

        item_transfer = item.get("transferinfo")
        if isinstance(item_transfer, dict):
            item_transfer = TransferInfo(**item_transfer)
        dest_fileitem: FileItem = item_transfer.target_item
        src_fileitem: FileItem = item.get("fileitem")

        if item_transfer.transfer_type != "move":
            return

        if dest_fileitem.storage != "u115" or src_fileitem.storage != "u115":
            return

        if not PathUtils.get_run_transfer_path(
            paths=configer.pan_transfer_paths,
            transfer_path=src_fileitem.path,
        ):
            return

        remove_id = ""
        # 遍历删除字典
        for key, item_list in pantransfercacher.top_delete_pan_transfer_list.items():
            # 只有目前处理完成的这个文件ID在处理列表中，才表明匹配到了该删除的顶层目录
            if str(dest_fileitem.fileid) in item_list:
                # 从列表中删除这个ID
                pantransfercacher.top_delete_pan_transfer_list[key] = [
                    item for item in item_list if item != str(dest_fileitem.fileid)
                ]
                # 记录需删除的顶层目录
                remove_id = key
                break

        if remove_id:
            # 只有需删除的顶层目录下面的文件全部整理完成才进行删除操作
            if not pantransfercacher.top_delete_pan_transfer_list.get(remove_id):
                del pantransfercacher.top_delete_pan_transfer_list[remove_id]
                resp = servicer.client.fs_delete(int(remove_id))
                if resp["state"]:
                    logger.info(f"【网盘整理】删除 {remove_id} 文件夹成功")
                else:
                    logger.error(f"【网盘整理】删除 {remove_id} 文件夹失败: {resp}")

        return

    @eventmanager.register(EventType.TransferComplete)
    def generate_strm(self, event: Event):
        """
        监控目录整理生成 STRM 文件
        """
        if (
            not configer.enabled
            or not configer.transfer_monitor_enabled
            or not configer.transfer_monitor_paths
            or not configer.moviepilot_address
        ):
            return

        item = event.event_data
        if not item:
            return

        strm_helper = TransferStrmHelper()
        strm_helper.do_generate(item, mediainfodownloader=servicer.mediainfodownloader)

    @eventmanager.register(EventType.PluginAction)
    def p115_full_sync(self, event: Event):
        """
        远程全量同步
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_full_sync":
            return
        post_message(
            channel=event.event_data.get("channel"),
            title=i18n.translate("start_full_sync"),
            userid=event.event_data.get("user"),
        )
        servicer.full_sync_strm_files()

    @eventmanager.register(EventType.PluginAction)
    def p115_inc_sync(self, event: Event):
        """
        远程增量同步
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_inc_sync":
            return
        post_message(
            channel=event.event_data.get("channel"),
            title=i18n.translate("start_inc_sync"),
            userid=event.event_data.get("user"),
        )
        servicer.increment_sync_strm_files(send_msg=True)

    @eventmanager.register(EventType.PluginAction)
    def p115_strm(self, event: Event):
        """
        全量生成指定网盘目录STRM
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_strm":
            return
        args = event_data.get("arg_str")
        if not args:
            logger.error(f"【全量STRM生成】缺少参数：{event_data}")
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_strm_parameter_error"),
                userid=event.event_data.get("user"),
            )
            return
        if (
            not configer.full_sync_strm_paths
            or not configer.moviepilot_address
            or not configer.user_download_mediaext
        ):
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_strm_full_sync_config_error"),
                userid=event.event_data.get("user"),
            )
            return

        status, paths = PathUtils.get_p115_strm_path(
            paths=configer.full_sync_strm_paths, media_path=args
        )
        if not status:
            post_message(
                channel=event.event_data.get("channel"),
                title=f"{args} {i18n.translate('p115_strm_match_path_error')}",
                userid=event.event_data.get("user"),
            )
            return
        strm_helper = FullSyncStrmHelper(
            client=servicer.client,
            mediainfodownloader=servicer.mediainfodownloader,
        )
        post_message(
            channel=event.event_data.get("channel"),
            title=i18n.translate("p115_strm_start_sync", paths=args),
            userid=event.event_data.get("user"),
        )
        strm_helper.generate_strm_files(
            full_sync_strm_paths=paths,
        )
        (
            strm_count,
            mediainfo_count,
            strm_fail_count,
            mediainfo_fail_count,
            remove_unless_strm_count,
        ) = strm_helper.get_generate_total()
        text = f"""
📂 网盘路径：{args}
📄 生成STRM文件 {strm_count} 个
⬇️ 下载媒体文件 {mediainfo_count} 个
❌ 生成STRM失败 {strm_fail_count} 个
🚫 下载媒体失败 {mediainfo_fail_count} 个
"""
        if remove_unless_strm_count != 0:
            text += f"🗑️ 清理无效STRM文件 {remove_unless_strm_count} 个"
        post_message(
            channel=event.event_data.get("channel"),
            userid=event.event_data.get("user"),
            title=i18n.translate("full_sync_done_title"),
            text=text,
        )

    @eventmanager.register(EventType.PluginAction)
    def p115_search(self, event: Event):
        """
        处理搜索请求
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "p115_search":
            return

        if not configer.tg_search_channels:
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_search_config_error"),
                userid=event.event_data.get("user"),
            )

        args = event_data.get("arg_str")
        if not args:
            logger.error(f"【搜索】缺少参数：{event_data}")
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_search_parameter_error"),
                userid=event.event_data.get("user"),
            )
            return

        try:
            session = session_manager.get_or_create(
                event_data, plugin_id=self.__class__.__name__
            )

            search_keyword = args.strip()

            if configer.nullbr_app_id and configer.nullbr_api_key:
                command = "search"
                view = "search_list"
            else:
                command = "resource"
                view = "resource_list"

            action = Action(command=command, view=view, value=search_keyword)

            immediate_messages = self.action_handler.process(session, action)
            # 报错，截断后续运行
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                return

            # 设置页面
            session.go_to(view)
            self._render_and_send(session)
        except Exception as e:
            logger.error(f"处理 search 命令失败: {e}", exc_info=True)

    @eventmanager.register(EventType.MessageAction)
    def message_action(self, event: Event):
        """
        处理按钮点击回调
        """
        try:
            event_data = event.event_data
            callback_text = event_data.get("text", "")

            # 1. 解码 Action callback_text = c:xxx|w:xxx|v|xxx
            session_id, action = decode_action(callback_text=callback_text)
            if not session_id or not action:
                # 如果解码失败或不属于本插件，则忽略
                return

            # 2. 获取会话
            session = session_manager.get(session_id)
            if not session:
                context = {
                    "channel": event_data.get("channel"),
                    "source": event_data.get("source"),
                    "userid": event_data.get("userid") or event_data.get("user"),
                    "original_message_id": event_data.get("original_message_id"),
                    "original_chat_id": event_data.get("original_chat_id"),
                }
                self.post_message(
                    **context,
                    title="⚠️ 会话已过期",
                    text="操作已超时。\n请重新发起 `/sh` 命令。",
                )
                return

            # 3. 更新会话上下文
            session.update_message_context(event_data)

            # 4. 委托给 ActionHandler 处理业务逻辑
            immediate_messages = self.action_handler.process(session, action)
            if immediate_messages:
                for msg in immediate_messages:
                    self.__send_message(session, text=msg.get("text"), title="错误")
                    return

            # 5. 渲染新视图并发送
            self._render_and_send(session)
        except Exception as e:
            logger.debug(f"出错了：{e}", exc_info=True)

    def _render_and_send(self, session: TSession):
        """
        根据 Session 的当前状态，渲染视图并发送/编辑消息。
        """
        # 1. 委托给 ViewRenderer 生成界面数据
        render_data = self.view_renderer.render(session)

        # 2. 发送或编辑消息
        self.__send_message(session, render_data=render_data)

        # 3. 处理会话结束逻辑
        if session.view.name in ["subscribe_success", "close"]:
            # 深复制会话的删除消息数据
            delete_message_data = deepcopy(session.get_delete_message_data())
            session_manager.end(session.session_id)
            # 等待一段时间让用户看到最后一条消息
            time.sleep(5)
            self.__delete_message(**delete_message_data)

    def __send_message(
        self, session: TSession, render_data: Optional[dict] = None, **kwargs
    ):
        """
        统一的消息发送接口。
        """
        context = asdict(session.message)
        if render_data:
            context.update(render_data)
        context.update(kwargs)
        # 将 user key改名成 userid，规避传入值只是user
        userid = context.get("user")
        if userid:
            context["userid"] = userid
            # 删除多余的 user 键
            context.pop("user", None)
        self.post_message(**context)

    def __delete_message(
        self,
        channel: MessageChannel,
        source: str,
        message_id: Union[str, int],
        chat_id: Optional[Union[str, int]] = None,
    ) -> bool:
        """
        删除会话中的原始消息。
        """
        # 兼容旧版本无删除方法
        if hasattr(self.chain, "delete_message"):
            return self.chain.delete_message(
                channel=channel, source=source, message_id=message_id, chat_id=chat_id
            )
        return False

    @eventmanager.register(EventType.UserMessage)
    def user_add_share(self, event: Event):
        """
        远程分享转存
        """
        if not configer.enabled:
            return
        text = event.event_data.get("text")
        userid = event.event_data.get("userid")
        channel = event.event_data.get("channel")
        if not text:
            return
        if not text.startswith("http"):
            return
        if not bool(
            re.match(r"^https?://(.*\.)?115[^/]*\.[a-zA-Z]{2,}(?:\/|$)", text)
        ) and not bool(
            re.match(
                r"^https?://(.*\.)?(alipan|aliyundrive)\.[a-zA-Z]{2,}(?:\/|$)", text
            )
        ):
            return
        servicer.sharetransferhelper.add_share(
            url=text,
            channel=channel,
            userid=userid,
        )
        return

    @eventmanager.register(EventType.PluginAction)
    def p115_add_share(self, event: Event):
        """
        远程分享转存
        """
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "p115_add_share":
                return
            args = event_data.get("arg_str")
            if not args:
                logger.error(f"【分享转存】缺少参数：{event_data}")
                post_message(
                    channel=event.event_data.get("channel"),
                    title=i18n.translate("p115_add_share_parameter_error"),
                    userid=event.event_data.get("user"),
                )
                return
        servicer.sharetransferhelper.add_share(
            url=args,
            channel=event.event_data.get("channel"),
            userid=event.event_data.get("user"),
        )
        return

    @eventmanager.register(EventType.PluginAction)
    def p115_add_offline(self, event: Event):
        """
        添加离线下载任务
        """
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "p115_add_offline":
                return
            args = event_data.get("arg_str")
            if not args:
                logger.error(f"【离线下载】缺少参数：{event_data}")
                post_message(
                    channel=event.event_data.get("channel"),
                    title=i18n.translate("p115_add_offline_parameter_error"),
                    userid=event.event_data.get("user"),
                )
                return
        if servicer.offlinehelper.add_urls_to_transfer([str(args)]):
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_add_offline_success"),
                userid=event.event_data.get("user"),
            )
        else:
            post_message(
                channel=event.event_data.get("channel"),
                title=i18n.translate("p115_add_offline_fail"),
                userid=event.event_data.get("user"),
            )

    @eventmanager.register(EventType.TransferComplete)
    def fix_monitor_life_strm(self, event: Event):
        """
        监控整理事件
        处理115生活事件生成MP整理STRM文件名称错误
        """

        def refresh_mediaserver(file_path: str, file_name: str):
            """
            刷新媒体服务器
            """
            if configer.monitor_life_media_server_refresh_enabled:
                if not servicer.monitorlife.monitor_life_service_infos:
                    return
                logger.info(f"【监控生活事件】 {file_name} 开始刷新媒体服务器")
                if configer.monitor_life_mp_mediaserver_paths:
                    status, mediaserver_path, moviepilot_path = (
                        PathUtils.get_media_path(
                            configer.monitor_life_mp_mediaserver_paths,
                            file_path,
                        )
                    )
                    if status:
                        logger.info(
                            f"【监控生活事件】 {file_name} 刷新媒体服务器目录替换中..."
                        )
                        file_path = file_path.replace(
                            moviepilot_path, mediaserver_path
                        ).replace("\\", "/")
                        logger.info(
                            f"【监控生活事件】刷新媒体服务器目录替换: {moviepilot_path} --> {mediaserver_path}"
                        )
                        logger.info(f"【监控生活事件】刷新媒体服务器目录: {file_path}")
                mediachain = MediaChain()
                meta = MetaInfoPath(path=Path(file_path))
                mediainfo = mediachain.recognize_media(meta=meta)
                if not mediainfo:
                    logger.warning(f"【监控生活事件】{file_name} 无法刷新媒体库")
                    return
                items = [
                    RefreshMediaItem(
                        title=mediainfo.title,
                        year=mediainfo.year,
                        type=mediainfo.type,
                        category=mediainfo.category,
                        target_path=Path(file_path),
                    )
                ]
                for (
                    name,
                    service,
                ) in servicer.monitorlife.monitor_life_service_infos.items():
                    if hasattr(service.instance, "refresh_library_by_items"):
                        service.instance.refresh_library_by_items(items)
                    elif hasattr(service.instance, "refresh_root_library"):
                        service.instance.refresh_root_library()
                    else:
                        logger.warning(f"【监控生活事件】{file_name} {name} 不支持刷新")

        def file_rename(fileitem: FileItem, refresh: bool = False):
            """
            重命名
            """
            if not fileitem:
                return
            target_path = Path(fileitem.path).parent
            file_item = lifeeventcacher.create_strm_file_dict.get(
                str(fileitem.fileid), None
            )
            if not file_item:
                return
            if fileitem.name != file_item[0]:
                # 文件名称不一致，表明网盘文件被重命名，需要将本地文件重命名
                target_file_path = Path(file_item[1]) / Path(
                    target_path / fileitem.name
                ).relative_to(file_item[2]).with_suffix(".strm")
                life_path = Path(file_item[1]) / Path(
                    target_path / file_item[0]
                ).relative_to(file_item[2]).with_suffix(".strm")
                # 如果重命名后的文件存在，先删除再重命名
                try:
                    if target_file_path.exists():
                        target_file_path.unlink(missing_ok=True)
                    life_path.rename(target_file_path)
                    _databasehelper.update_path_by_id(
                        id=int(fileitem.fileid),
                        new_path=Path(target_path / fileitem.name).as_posix(),
                    )
                    _databasehelper.update_name_by_id(
                        id=int(fileitem.fileid),
                        new_name=str(fileitem.name),
                    )
                    lifeeventcacher.create_strm_file_dict.pop(
                        str(fileitem.fileid), None
                    )
                    logger.info(
                        f"【监控生活事件】修正文件名称: {life_path} --> {target_file_path}"
                    )
                    if refresh:
                        refresh_mediaserver(
                            file_path=Path(target_file_path).as_posix(),
                            file_name=str(target_file_path.name),
                        )
                    return
                except Exception as e:
                    logger.error(f"【监控生活事件】修正文件名称失败: {e}")

        # 生活事件已开启
        if (
            not configer.monitor_life_enabled
            or not configer.monitor_life_paths
            or not configer.monitor_life_event_modes
        ):
            return

        # 生活事件在运行
        if not bool(
            servicer.monitor_life_thread and servicer.monitor_life_thread.is_alive()
        ):
            return

        item = event.event_data
        if not item:
            return

        # 整理信息
        item_transfer = item.get("transferinfo")
        if isinstance(item_transfer, dict):
            item_transfer = TransferInfo(**item_transfer)
        # 目的地文件 fileitem
        dest_fileitem: FileItem = item_transfer.target_item
        # 目标字幕文件清单
        subtitle_list = getattr(item_transfer, "subtitle_list_new", [])
        # 目标音频文件清单
        audio_list = getattr(item_transfer, "audio_list_new", [])

        _databasehelper = FileDbHelper()

        file_rename(fileitem=dest_fileitem, refresh=True)

        storagechain = StorageChain()
        if subtitle_list:
            for _path in subtitle_list:
                fileitem = storagechain.get_file_item(storage="u115", path=Path(_path))
                file_rename(fileitem=fileitem)

        if audio_list:
            for _path in audio_list:
                fileitem = storagechain.get_file_item(storage="u115", path=Path(_path))
                file_rename(fileitem=fileitem)

    def stop_service(self):
        """
        退出插件
        """
        servicer.stop()
        ct_db_manager.close_database()
        U115Patcher().disable()
        
        # 停止WebDAV服务
        webdav_service.stop()

    async def _save_config_api(self, request: Request) -> Dict:
        """
        异步保存配置
        """
        try:
            data = await request.json()
            if not configer.update_config(data):
                return {"code": 1, "msg": "保存失败，请查看详细日志"}

            # 持久化存储配置
            configer.update_plugin_config()

            i18n.load_translations()

            sentry_manager.reload_config()

            # 重新初始化插件
            self.init_plugin(config=self.get_config())

            return {"code": 0, "msg": "保存成功"}
        except Exception as e:
            return {"code": 1, "msg": f"保存失败: {str(e)}"}
