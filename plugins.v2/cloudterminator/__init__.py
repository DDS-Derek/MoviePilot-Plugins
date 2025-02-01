import sys
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import List, Dict, Tuple, Optional, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from app.log import logger
from app.core.config import settings
from app.plugins import _PluginBase
from app.schemas import NotificationType

from .clouddisk.u115 import u115_manager
from .db_manager import ct_db_manager
from .db_manager.init import init_db, update_db
from ...core.event import eventmanager, Event
from ...schemas.types import EventType

notify_lock = threading.Lock()


class CloudTerminator(_PluginBase):
    # 插件名称
    plugin_name = "云盘 302 服务器"
    # 插件描述
    plugin_desc = "用于快速搭建云盘 302 服务器，"
    # 插件图标
    plugin_icon = "Synomail_A.png"
    # 插件版本
    plugin_version = "0.1"
    # 插件作者
    plugin_author = "DDS-Derek"
    # 作者主页
    author_url = "https://github.com/DDS-Derek"
    # 插件配置项ID前缀
    plugin_config_prefix = "cloudterminator_"
    # 加载顺序
    plugin_order = 29
    # 可使用的用户级别，0为所有用户级，1为认证后才显示
    auth_level = 0

    _scheduler: Optional[BackgroundScheduler] = BackgroundScheduler(timezone=settings.TZ)
    _event = threading.Event()

    # 用于快速新增配置项，调用时，要加 _ 前缀，如：_enabled
    __default_config = {
        'enabled': False,
        'delete_db': False,

        'notify': False,
        'notify_level': 'ALL',
        'notify_type': 'Plugin',

        'moviepilot_url': None,

        'u115_onlyonce': False,
        'u115_path': None,
        'u115_strm_path': None,
        'u115_cookie': None,

        'u123_onlyonce': False,
        'u123_path': None,
        'u123_strm_path': None,
        'u123_cookie': None,
    }

    @staticmethod
    def logs_oper(oper_name: str):
        """
        数据库操作汇报装饰器
        - 捕获异常并记录日志
        - 5秒内合并多条消息，避免频繁发送通知
        """

        def decorator(func):
            @wraps(func)
            def wrapper(self,*args, **kwargs):
                level, text = 'success', f"{oper_name} 成功"
                try:
                    result = func(self, *args, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"{oper_name} 失败：{str(e)}", exc_info=True)
                    level, text = 'error', f"{oper_name} 失败：{str(e)}"
                    return False
                finally:
                    if hasattr(self, 'add_message'):
                        self.add_message(title=oper_name, text=text, level=level)

            return wrapper

        return decorator

    def __init__(self):
        """
        初始化
        """
        super().__init__()
        # 类名小写
        class_name = self.__class__.__name__.lower()
        # 数据库迁移脚本路径
        self.__database_path = settings.ROOT_PATH / 'app/plugins' / class_name / "database"
        # 数据库路径
        self.__db_path = settings.PLUGIN_DATA_PATH / class_name / "db"
        # 日志路径
        self.__logs_dir = settings.PLUGIN_DATA_PATH / class_name / "logs"
        # 数据库文件名
        self.__db_filename = "cloudterminator.db"
        # 302重定向日志文件名
        self.__302_server_log_filename = "pan302.log"
        # 消息存储
        self.__messages = {}
        # 115网盘客户端
        self.__u115_client = None
        # 初始化数据库
        self.init_database()

    def __getattr__(self, key):
        """
        动态获取配置项 - 解决IDE警告
        """
        if key.startswith('_') and key[1:] in self.__default_config.keys():
            if key not in self.__dict__:
                self.__dict__[key] = self.__default_config[key[1:]]
            return self.__dict__[key]

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            default_config_keys = self.__default_config.keys()
            for key in config.keys():
                if key in default_config_keys:
                    setattr(self, f"_{key}", config[key])
            self.__update_config()

        # if self.__check_python_version() is False:
        #     self._enabled, self._onlyonce = False, False
        #     self.__update_config()
        #     return False

        self.init_database()
        self.once_run()
        self.start()

    def get_state(self):
        """
        获取插件状态
        """
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API
        [{
            "path": "/xx",
            "endpoint": self.xxx,
            "methods": ["GET", "POST"],
            "summary": "API名称",
            "description": "API说明"
        }]
        """
        apis = []
        return apis

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({
                "title": item.value,
                "value": item.name
            })

        MsgLevelOptions = [
            {"title": "全部", "value": "ALL"},
            {"title": "仅错误", "value": "ERROR"},
            {"title": "仅成功", "value": "SUCCESS"},
            {"title": "不汇报", "value": "SILENCE"}
        ]

        # Todo：空组件占位符
        under_development = [{
            'component': 'VEmptyState',
            'text': '预留项，待更新',
            'props': {
                'class': 'text-center',
            }
        }]

        # Todo: 发版时改true
        if self.__check_python_version() is False:
            content = [
                {
                    'component': 'VForm',
                    'content': [
                        {
                            'component': 'VRow',
                            'props': {
                                'align': 'center',
                            },
                            'content': [
                                {
                                    'component': 'VCol',
                                    'props': {
                                        'model': 'tabs',
                                        'cols': 12,
                                        'md': 4,
                                    },
                                    'content': [
                                        {
                                            'component': 'VSwitch',
                                            'props': {
                                                'model': 'enabled_notify',
                                                'label': '启用插件',
                                                'hint': '同步启动 302 代理服务器',
                                                'persistent-hint': True,
                                            }
                                        }
                                    ]
                                },
                                {
                                    'component': 'VCol',
                                    'props': {
                                        'cols': 12,
                                        'md': 4,
                                    },
                                    'content': [
                                        {
                                            'component': 'VAlert',
                                            'props': {
                                                'type': 'error',
                                                'variant': 'tonal',
                                                'text': '删除数据库不可恢复！慎用！',
                                            }
                                        }
                                    ]
                                },
                                {
                                    'component': 'VCol',
                                    'props': {
                                        'cols': 12,
                                        'md': 4,
                                    },
                                    'content': [
                                        {
                                            'component': 'VSwitch',
                                            'props': {
                                                'model': 'delete_db',
                                                'label': '删除数据库',
                                                'hint': '删除数据库，清空所有数据',
                                                'persistent-hint': True,
                                            }
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            'component': 'VTabs',
                            'props': {
                                'model': '_tabs',
                                'height': 72,
                                'style': {
                                    'margin-top': '8px',
                                    'margin-bottom': '10px',
                                },
                                'stacked': True,
                                'fixed-tabs': True
                            },
                            'content': [
                                {
                                    'component': 'VTab',
                                    'props': {
                                        'value': 'basic_tab',
                                    },
                                    'text': '基础设置'

                                },
                                {
                                    'component': 'VTab',
                                    'props': {
                                        'value': 'u115_tab',
                                    },
                                    'text': '115网盘'

                                },
                                {
                                    'component': 'VTab',
                                    'props': {
                                        'value': 'u123_tab',
                                    },
                                    'text': '123网盘'
                                },
                            ],
                        },
                        {
                            'component': 'VWindow',
                            'props': {
                                'model': '_tabs',
                                'class': 'py-3',
                            },
                            'content': [
                                {
                                    'component': 'VWindowItem',
                                    'props': {
                                        'value': 'basic_tab',
                                    },
                                    'content': [
                                        {
                                            'component': 'VRow',
                                            'props': {
                                                'align': 'center',
                                            },
                                            'content': [
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 4,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VSwitch',
                                                            'props': {
                                                                'model': 'notify',
                                                                'label': '发送通知',
                                                                'hint': '任务完成时，发送结果通知',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 4,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VAutocomplete',
                                                            'props': {
                                                                'model': 'notify_level',
                                                                'label': '通知等级',
                                                                'items': MsgLevelOptions,
                                                                'hint': '控制消息推送量',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 4,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VAutocomplete',
                                                            'props': {
                                                                'model': 'notify_type',
                                                                'label': '通知类型',
                                                                'items': MsgTypeOptions,
                                                                'hint': '自定义消息的类型',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                            ]
                                        },
                                        {
                                            'component': 'VRow',
                                            'props': {
                                                'align': 'center',
                                            },
                                            'content': [
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 12,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VTextField',
                                                            'props': {
                                                                'model': 'moviepilot_url',
                                                                'label': 'MoviePilot API URL',
                                                                'clearable': True,
                                                                'hint': '302访问用的url',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                            ]
                                        },
                                    ]
                                },
                                {
                                    'component': 'VWindowItem',
                                    'props': {
                                        'value': 'u115_tab'
                                    },
                                    'content': [
                                        {
                                            'component': 'VRow',
                                            'props': {
                                                'align': 'center',
                                                'class': 'mt-1',
                                            },
                                            'content': [
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 4,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VSwitch',
                                                            'props': {
                                                                'model': 'u115_onlyonce',
                                                                'label': '立刻同步',
                                                                'hint': '一次性任务；运行后关闭',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 12,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VTextField',
                                                            'props': {
                                                                'model': 'u115_strm_path',
                                                                'label': 'STRM 生成路径',
                                                                'clearable': True,
                                                                'hint': 'STRM 生成路径',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                        'md': 12,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VTextField',
                                                            'props': {
                                                                'model': 'u115_path',
                                                                'label': '网盘媒体文件储存路径',
                                                                'clearable': True,
                                                                'hint': '网盘媒体文件储存路径',
                                                                'persistent-hint': True,
                                                            }
                                                        }
                                                    ]
                                                },
                                            ]
                                        },
                                        {
                                            'component': 'VRow',
                                            'props': {
                                                'align': 'center',
                                            },
                                            'content': [
                                                {
                                                    'component': 'VCol',
                                                    'props': {
                                                        'cols': 12,
                                                    },
                                                    'content': [
                                                        {
                                                            'component': 'VTextarea',
                                                            'props': {
                                                                'model': 'u115_cookie',
                                                                'label': 'cookie',
                                                                'placeholder': f'UID=***_**_***;\nCID=***;\nSEID=***',
                                                                'hint': '当前使用的认证缓存。清空时保存，将删除已存在的参数值。可手动替换，使用英文分号;分割，当前只支持普通文本格式，不支持json格式',
                                                                'persistent-hint': True,
                                                                'active': True,
                                                                'clearable': True,
                                                                'auto-grow': True,
                                                            }
                                                        },
                                                    ]
                                                },
                                            ]
                                        },
                                    ],
                                },
                                {
                                    'component': 'VWindowItem',
                                    'props': {
                                        'value': 'u123_tab',
                                    },
                                    'content': under_development,
                                },
                            ]
                        },
                    ]
                },
            ]
        else:
            content = [{
                'component': 'VEmptyState',
                'text': '当前MoviePilot使用的Python版本不支持本插件，请升级到Python 3.12及以上的分支版本使用！',
                'props': {
                    'class': 'text-center',
                }
            }]

        return content, self.__default_config

    def get_page(self) -> List[dict]:
        return [
            {
                'component': 'VRow',
                'props': {
                    'style': {
                        'overflow': 'hidden',
                    }
                },
                'content':
                    self.__u115_page()
                    # self.__u123_page()
            }
        ]

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown(wait=False)
                    self._event.clear()
                self._scheduler = None
            self.close_database()
            # todo:停止302
        except Exception as e:
            logger.info(f"插件停止错误: {str(e)}", exc_info=True)

    """ start """

    def start(self):
        """
        启动插件
        """
        try:
            pass
        except Exception as e:
            logger.info(f"插件启动错误: {str(e)}", exc_info=True)
            if self._enabled:
                self._enabled = False
            if self._onlyonce:
                self._onlyonce = False
        finally:
            self.__update_config()

    """ 115云盘 """

    def get_u115_client(self):
        """
        获取115云盘客户端
        """
        if not self._u115_cookie:
            return None
        if not self.__u115_client:
            self.__u115_client = u115_manager.connect(self._u115_cookie)
        return True

    def close_u115_client(self):
        """
        关闭115云盘客户端
        """
        if self._u115_client:
            u115_manager.disconnect(self.__u115_client)
        # 清除客户端的缓存
        self.__u115_client = None

    # todo：2.2.7新增整理链式，后续替换
    @eventmanager.register(EventType.TransferComplete)
    @logs_oper("115云盘STRM")
    def sync_u115_strm(self, event: Event) -> bool:
        """
        自动增量式同步STRM
        """
        try:
            self.__sync_u115_strm()
            return True
        except Exception as e:
            raise e

    @logs_oper(oper_name="全量同步")
    def all_sync_u115_strm(self) -> bool:
        """
        手动全量式同步STRM
        """
        try:
            self.__sync_u115_strm()
            return True
        except Exception as e:
            raise e
        finally:
            self._u115_onlyonce = False
            self.__update_config()

    def __sync_u115_strm(self) -> bool:
        """
        手动全量与自动增量的共同逻辑
        """
        pass

    """ 302 server"""

    @staticmethod
    def u115_proxy_302_server(method, path, json):
        """
        302 代理服务器
        :param method: 请求方法, GET/POST/PUT/DELETE
        :param path: 请求路径
        :param json: 请求参数
        :return:
        """
        try:
            pass
        except Exception as e:
            raise e

    """ db manager """

    @logs_oper("初始化数据库")
    def init_database(self) -> bool:
        """
        初始化数据库
        """
        if not ct_db_manager.is_initialized():
            # 初始化数据库会话
            ct_db_manager.init_database(db_path=self.__db_path, db_filename=self.__db_filename)
            # 表单补全
            init_db(engine=ct_db_manager.Engine)
            # 更新数据库
            update_db(db_dir=self.__db_path, db_filename=self.__db_filename, database_dir=self.__database_path)
        return True

    @logs_oper("关闭数据库")
    def close_database(self) -> bool:
        """
        关闭数据库
        """
        if ct_db_manager.is_initialized():
            ct_db_manager.close_database()
        return True

    @logs_oper("删除数据库")
    def delete_database(self) -> bool:
        """
        删除数据库
        """
        # 关闭连接后，用pathlib模块直接删除数据库文件 路径为 self.__db_path / self.__db_filename
        if ct_db_manager.is_initialized():
            ct_db_manager.close_database()
        db_file_path = self.__db_path / self.__db_filename
        if db_file_path.exists():
            db_file_path.unlink()
        return True

    """ utils """

    @staticmethod
    def __check_python_version() -> bool:
        """
        检查Python版本
        """
        if not (sys.version_info.major == 3 and sys.version_info.minor >= 12):
            logger.error("当前MoviePilot使用的Python版本不支持本插件，请升级到Python 3.12及以上的分支版本使用！")
            return False
        return True

    def __update_config(self):
        """
        更新配置
        """
        config = {}
        keys = self.__default_config.keys()
        for key in keys:
            config[key] = getattr(self, f"_{key}") if hasattr(self, f"_{key}") else self.__default_config[key]
        self.update_config(config)

    """ notify """

    def add_message(self, level: str, title: str, text: str):
        """
        添加新消息，并分类存储
        """
        with notify_lock:
            if not self._notify:
                return
            # 静默无需记录通知
            if self._notify_level == "SILENCE":
                return
            if level not in ["success", "error"]:
                logger.error(f"无效的消息等级: {level}")
                return

            # 等级不存在，则初始化
            if level not in self.__messages:
                self.__messages[level] = {}
            # 主题不存在，则初始化
            if title not in self.__messages[level]:
                self.__messages[level][title] = {}

            # 生成唯一 ID（时间戳）
            msg_id = time.time()

            # 添加新消息
            self.__messages[level][title][msg_id] = text

            logger.debug(f"[{time.strftime('%H:%M:%S')}] 新消息添加: {level} -  {title} - {text}")

            # 取消旧的定时器，并重新启动，success 与 error 消息各一个，防止消息堆积
            if self._scheduler.get_job(f"send_{level}_messages"):
                self._scheduler.remove_job(f"send_{level}_messages")

            run_time = datetime.now() + timedelta(seconds=5)
            self._scheduler.add_job(func=self._send_messages,
                                    kwargs={"level": level},
                                    trigger=DateTrigger(run_date=run_time),
                                    id=f"send_{level}_messages")

    def _send_messages(self, level: str):
        """
        触发发送并清理已发送消息
        """
        with notify_lock:
            if not self.__messages[level]:
                return

            # 复制数据到 待发送队列
            pending_messages = {
                level: {title: text.copy() for title, text in self.__messages[level].items()}
            }

            if self._notify_level == "SILENCE":
                return True
            if self._notify_level == "ALL" or self._notify_level == level.upper():
                body = self.__build_message(pending_messages)

                self.post_message(mtype=getattr(NotificationType, self._notify_type, NotificationType.Plugin.value),
                                  title=f"{self.plugin_name} - 运行{'失败' if level == 'error' else '成功'}",
                                  text=body)

    @staticmethod
    def __build_message_body(pending_messages: dict) -> str:
        """
        构建消息体

        :param pending_messages: 待发送的消息
        :return:
        title1: 标题\n
        - text1\n
        - text2\n
        title2: 标题\n
        - text3\n
        - text4\n
        """
        body = ""
        for level, topics in pending_messages.items():
            for title, msgs in topics.items():
                body += f"{title}\n"
                for msg in msgs.values():
                    body += f"- {msg}\n"
        return body
