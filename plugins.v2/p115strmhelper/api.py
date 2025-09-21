import base64
import io
import time
from datetime import datetime
from dataclasses import asdict
from typing import Dict, Any, Optional
from pathlib import Path
from urllib.parse import quote

import qrcode
import requests
from orjson import dumps, loads
from p115client import P115Client
from p115client.exception import DataError
from p115client.tool.fs_files import iter_fs_files
from fastapi import Request, Response

from .service import servicer
from .core.config import configer
from .core.cache import idpathcacher
from .core.message import post_message
from .core.i18n import i18n
from .core.aliyunpan import AliyunPanLogin
from .utils.sentry import sentry_manager
from .utils.oopserver import OOPServerHelper
from .helper.webdav import webdav_service

from app.log import logger
from app.core.cache import cached, TTLCache
from app.helper.mediaserver import MediaServerHelper
from app.schemas import NotificationType


@sentry_manager.capture_all_class_exceptions
class Api:
    """
    插件 API
    """

    def __init__(self, client: Optional[P115Client]):
        self._client = client

        self.browse_dir_pan_api_cache = TTLCache(
            maxsize=1024, ttl=120, region="p115strmhelper_api_browse_dir_api"
        )
        self.browse_dir_pan_api_last = 0

    @staticmethod
    def get_config_api() -> Dict:
        """
        获取配置
        """
        config = configer.get_all_configs()

        mediaserver_helper = MediaServerHelper()
        config["mediaservers"] = [
            {"title": config.name, "value": config.name}
            for config in mediaserver_helper.get_configs().values()
        ]
        return config

    @staticmethod
    def get_machine_id_api() -> Dict:
        """
        获取 Machine ID
        """
        return {"machine_id": configer.get_config("MACHINE_ID")}

    @cached(
        region="p115strmhelper_api_get_user_storage_status", ttl=60 * 60, skip_none=True
    )
    def get_user_storage_status(self) -> Dict[str, Any]:
        """
        获取115用户基本信息和空间使用情况。
        """
        if not configer.get_config("cookies"):
            return {
                "success": False,
                "error_message": "115 Cookies 未配置，无法获取信息。",
                "user_info": None,
                "storage_info": None,
            }

        try:
            if not self._client:
                try:
                    _temp_client = P115Client(configer.get_config("cookies"))
                    logger.info("【用户存储状态】P115Client 初始化成功")
                except Exception as e:
                    logger.error(f"【用户存储状态】P115Client 初始化失败: {e}")
                    return {
                        "success": False,
                        "error_message": f"115客户端初始化失败: {e}",
                        "user_info": None,
                        "storage_info": None,
                    }
            else:
                _temp_client = self._client

            # 获取用户信息
            user_info_resp = _temp_client.user_my_info()
            user_details: Dict = {}
            if user_info_resp.get("state"):
                data = user_info_resp.get("data", {})
                vip_data = data.get("vip", {})
                face_data = data.get("face", {})
                user_details = {
                    "name": data.get("uname"),
                    "is_vip": vip_data.get("is_vip"),
                    "is_forever_vip": vip_data.get("is_forever"),
                    "vip_expire_date": vip_data.get("expire_str")
                    if not vip_data.get("is_forever")
                    else "永久",
                    "avatar": face_data.get("face_s"),
                }
                logger.info(
                    f"【用户存储状态】获取用户信息成功: {user_details.get('name')}"
                )
            else:
                error_msg = (
                    user_info_resp.get("message", "获取用户信息失败")
                    if user_info_resp
                    else "获取用户信息响应为空"
                )
                logger.error(f"【用户存储状态】获取用户信息失败: {error_msg}")
                return {
                    "success": False,
                    "error_message": f"获取115用户信息失败: {error_msg}",
                    "user_info": None,
                    "storage_info": None,
                }

            # 获取空间信息
            space_info_resp = _temp_client.fs_index_info(payload=0)
            storage_details = None
            if space_info_resp.get("state"):
                data = space_info_resp.get("data", {}).get("space_info", {})
                storage_details = {
                    "total": data.get("all_total", {}).get("size_format"),
                    "used": data.get("all_use", {}).get("size_format"),
                    "remaining": data.get("all_remain", {}).get("size_format"),
                }
                logger.info(
                    f"【用户存储状态】获取空间信息成功: 总-{storage_details.get('total')}"
                )
            else:
                error_msg = (
                    space_info_resp.get("error", "获取空间信息失败")
                    if space_info_resp
                    else "获取空间信息响应为空"
                )
                logger.error(f"【用户存储状态】获取空间信息失败: {error_msg}")
                return {
                    "success": False,
                    "error_message": f"获取115空间信息失败: {error_msg}",
                    "user_info": user_details,
                    "storage_info": None,
                }

            return {
                "success": True,
                "user_info": user_details,
                "storage_info": storage_details,
            }

        except Exception as e:
            logger.error(f"【用户存储状态】获取信息时发生意外错误: {e}", exc_info=True)
            error_str_lower = str(e).lower()
            if (
                isinstance(e, DataError)
                and ("errno 61" in error_str_lower or "enodata" in error_str_lower)
                and "<!doctype html>" in error_str_lower
            ):
                specific_error_message = "获取115账户信息失败：Cookie无效或已过期，请在插件配置中重新扫码登录。"
            elif (
                "cookie" in error_str_lower
                or "登录" in error_str_lower
                or "登陆" in error_str_lower
            ):
                specific_error_message = (
                    f"获取115账户信息失败：{str(e)} 请检查Cookie或重新登录。"
                )
            else:
                specific_error_message = f"处理请求时发生错误: {str(e)}"

            result_to_return = {
                "success": False,
                "error_message": specific_error_message,
                "user_info": None,
                "storage_info": None,
            }
            return result_to_return

    def browse_dir_api(self, request: Request) -> Dict:
        """
        浏览目录
        """
        path = Path(request.query_params.get("path", "/"))
        is_local = request.query_params.get("is_local", "false").lower() == "true"
        if is_local:
            try:
                if not path.exists():
                    return {"code": 1, "msg": f"目录不存在: {path}"}
                dirs = []
                files = []
                for item in path.iterdir():
                    if item.is_dir():
                        dirs.append(
                            {"name": item.name, "path": str(item), "is_dir": True}
                        )
                    else:
                        files.append(
                            {"name": item.name, "path": str(item), "is_dir": False}
                        )
                return {
                    "code": 0,
                    "path": path,
                    "items": sorted(dirs, key=lambda x: x["name"]),
                }
            except Exception as e:
                return {"code": 1, "msg": f"浏览本地目录失败: {str(e)}"}
        else:
            if not self._client or not configer.get_config("cookies"):
                return {"code": 1, "msg": "未配置cookie或客户端初始化失败"}

            if time.time() - self.browse_dir_pan_api_last < 2:
                logger.debug("浏览网盘目录 API 限流，等待 2s 后继续")
                time.sleep(2)

            try:
                items = self.browse_dir_pan_api_cache.get(key=path.as_posix())
                if items:
                    return items

                if path.as_posix() == "/":
                    cid = 0
                else:
                    dir_info = self._client.fs_dir_getid(path.as_posix())
                    if not dir_info:
                        return {"code": 1, "msg": f"获取目录ID失败: {path}"}
                    cid = int(dir_info["id"])

                items = []
                for batch in iter_fs_files(self._client, cid, cooldown=2):
                    for item in batch.get("data", []):
                        if "fid" not in item:
                            idpathcacher.add_cache(
                                id=int(item.get("cid")),
                                directory=f"{path.as_posix().rstrip('/')}/{item.get('n')}",
                            )
                            items.append(
                                {
                                    "name": item.get("n"),
                                    "path": f"{path.as_posix().rstrip('/')}/{item.get('n')}",
                                    "is_dir": True,
                                }
                            )
                self.browse_dir_pan_api_last = time.time()
                items = {
                    "code": 0,
                    "path": path.as_posix(),
                    "items": sorted(items, key=lambda x: x["name"]),
                }
                self.browse_dir_pan_api_cache.set(key=path.as_posix(), value=items)
                return items
            except Exception as e:
                logger.error(f"浏览网盘目录 API 原始错误: {str(e)}")
                return {"code": 1, "msg": f"浏览网盘目录失败: {str(e)}"}

    @staticmethod
    def get_qrcode_api(
        request: Request = None, client_type_override: Optional[str] = None
    ) -> Dict:
        """
        获取登录二维码
        """
        try:
            final_client_type = client_type_override
            if not final_client_type:
                final_client_type = (
                    request.query_params.get("client_type", "alipaymini")
                    if request
                    else "alipaymini"
                )
            # 二维码支持的客户端类型验证
            allowed_types = [
                "web",
                "android",
                "115android",
                "ios",
                "115ios",
                "alipaymini",
                "wechatmini",
                "115ipad",
                "tv",
                "qandroid",
            ]
            if final_client_type not in allowed_types:
                final_client_type = "alipaymini"

            logger.info(f"【扫码登入】二维码API - 使用客户端类型: {final_client_type}")

            resp = requests.get(
                "https://qrcodeapi.115.com/api/1.0/web/1.0/token/", timeout=10
            )
            if not resp.ok:
                error_msg = f"获取二维码token失败: {resp.status_code} - {resp.text}"
                return {
                    "code": -1,
                    "error": error_msg,
                    "message": error_msg,
                    "success": False,
                }
            resp_info = resp.json().get("data", {})
            uid = resp_info.get("uid", "")
            _time = resp_info.get("time", "")
            sign = resp_info.get("sign", "")

            resp = requests.get(
                f"https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid={uid}",
                timeout=10,
            )
            if not resp.ok:
                error_msg = f"获取二维码图片失败: {resp.status_code} - {resp.text}"
                return {
                    "code": -1,
                    "error": error_msg,
                    "message": error_msg,
                    "success": False,
                }

            qrcode_base64 = base64.b64encode(resp.content).decode("utf-8")

            tips_map = {
                "alipaymini": "请使用115客户端或支付宝扫描二维码登录",
                "wechatmini": "请使用115客户端或微信扫描二维码登录",
                "android": "请使用115安卓客户端扫描登录",
                "115android": "请使用115安卓客户端扫描登录",
                "ios": "请使用115 iOS客户端扫描登录",
                "115ios": "请使用115 iOS客户端扫描登录",
                "web": "请使用115网页版扫码登录",
                "115ipad": "请使用115 PAD客户端扫描登录",
                "tv": "请使用115 TV客户端扫描登录",
                "qandroid": "请使用115 qandroid客户端扫描登录",
            }
            tips = tips_map.get(final_client_type, "请扫描二维码登录")

            return {
                "code": 0,
                "uid": uid,
                "time": _time,
                "sign": sign,
                "qrcode": f"data:image/png;base64,{qrcode_base64}",
                "tips": tips,
                "client_type": final_client_type,
                "success": True,
            }

        except Exception as e:
            logger.error(f"【扫码登入】获取二维码异常: {e}", exc_info=True)
            return {
                "code": -1,
                "error": f"获取登录二维码出错: {str(e)}",
                "message": f"获取登录二维码出错: {str(e)}",
                "success": False,
            }

    def _check_qrcode_api_internal(
        self,
        uid: str,
        _time: str,
        sign: str,
        client_type: str,
    ) -> Dict:
        """
        检查二维码状态并处理登录
        """
        try:
            if not uid:
                error_msg = "无效的二维码ID，参数uid不能为空"
                return {"code": -1, "error": error_msg, "message": error_msg}

            resp = requests.get(
                f"https://qrcodeapi.115.com/get/status/?uid={uid}&time={_time}&sign={sign}",
                timeout=120,
            )
            status_code = resp.json().get("data").get("status")
        except Exception as e:
            error_msg = f"检查二维码状态异常: {str(e)}"
            logger.error(f"【扫码登入】检查二维码状态异常: {e}", exc_info=True)
            return {"code": -1, "error": error_msg, "message": error_msg}

        status_map = {
            0: {"code": 0, "status": "waiting", "msg": "等待扫码"},
            1: {"code": 0, "status": "scanned", "msg": "已扫码，等待确认"},
            2: {"code": 0, "status": "success", "msg": "已确认，正在登录"},
            -1: {"code": -1, "error": "二维码已过期", "message": "二维码已过期"},
            -2: {"code": -1, "error": "用户取消登录", "message": "用户取消登录"},
        }

        if status_code in status_map:
            result = status_map[status_code].copy()
            if status_code == 2:
                try:
                    resp = requests.post(
                        f"https://passportapi.115.com/app/1.0/{client_type}/1.0/login/qrcode/",
                        data={"app": client_type, "account": uid},
                        timeout=10,
                    )
                    login_data = resp.json()
                except Exception as e:
                    return {
                        "code": -1,
                        "error": f"获取登录结果请求失败: {e}",
                        "message": f"获取登录结果请求失败: {e}",
                    }

                if login_data.get("state") and login_data.get("data"):
                    cookie_data = login_data.get("data", {})
                    cookie_string = ""
                    if "cookie" in cookie_data and isinstance(
                        cookie_data["cookie"], dict
                    ):
                        for name, value in cookie_data["cookie"].items():
                            if name and value:
                                cookie_string += f"{name}={value}; "
                    if cookie_string:
                        _cookies = cookie_string.strip()
                        configer.update_config({"cookies": _cookies})
                        configer.update_plugin_config()
                        try:
                            self._client = P115Client(_cookies)
                            result["cookie"] = cookie_string
                        except Exception as ce:
                            return {
                                "code": -1,
                                "error": f"Cookie获取成功，但客户端初始化失败: {str(ce)}",
                                "message": f"Cookie获取成功，但客户端初始化失败: {str(ce)}",
                            }
                    else:
                        return {
                            "code": -1,
                            "error": "登录成功但未能正确解析Cookie",
                            "message": "登录成功但未能正确解析Cookie",
                        }
                else:
                    specific_error = login_data.get(
                        "message", login_data.get("error", "未知错误")
                    )
                    return {
                        "code": -1,
                        "error": f"获取登录会话数据失败: {specific_error}",
                        "message": f"获取登录会话数据失败: {specific_error}",
                    }
            return result
        elif status_code is None:
            if resp.json().get("message", None) == "key invalid":
                return status_map[-1].copy()
            return status_map[0].copy()
        else:
            return {
                "code": -1,
                "error": f"未知的115业务状态码: {status_code}",
                "message": f"未知的115业务状态码: {status_code}",
            }

    def check_qrcode_api(self, request: Request) -> Dict:
        """
        检查二维码状态
        """
        uid = request.query_params.get("uid", "")
        _time = request.query_params.get("time", "")
        sign = request.query_params.get("sign", "")
        client_type = request.query_params.get("client_type", "alipaymini")
        return self._check_qrcode_api_internal(
            uid=uid, _time=_time, sign=sign, client_type=client_type
        )

    @staticmethod
    def get_aliyundrive_qrcode_api():
        """
        获取阿里云盘登入二维码
        """
        try:
            data = AliyunPanLogin.qr().get("content").get("data")
            if data:
                code_content = data.get("codeContent")
                t_param = data.get("t")
                ck_param = data.get("ck")

                img = qrcode.make(code_content)
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_bytes = buffered.getvalue()
                base64_encoded_string = base64.b64encode(img_bytes)
                base64_string = base64_encoded_string.decode("utf-8")
                data_url = f"data:image/png;base64,{base64_string}"

                response_data = {
                    "code": 0,
                    "msg": "获取成功",
                    "qrcode": data_url,
                    "t": t_param,
                    "ck": ck_param,
                }
                return response_data
            else:
                return {"code": -1, "msg": "获取二维码失败，无有效数据"}

        except Exception as e:
            return {"code": -1, "msg": f"获取二维码失败: {e}"}

    @staticmethod
    def check_aliyundrive_qrcode_api(request: Request):
        """
        轮询检查二维码的扫描和确认状态
        """
        t_param = request.query_params.get("t")
        ck_param = request.query_params.get("ck")
        try:
            data = AliyunPanLogin.ck(t_param, ck_param).get("content")
            if data["data"]["qrCodeStatus"] == "CONFIRMED":
                h = data["data"]["bizExt"]
                c = loads(base64.b64decode(h).decode("gbk"))
                refresh_token = c["pds_login_result"]["refreshToken"]
                if refresh_token:
                    configer.update_config({"aliyundrive_token": refresh_token})
                    configer.update_plugin_config()
                    return {
                        "code": 0,
                        "status": "success",
                        "msg": "登录成功",
                        "token": refresh_token,
                    }
                return {
                    "code": -1,
                    "status": "error",
                    "msg": "登录成功但未能获取Token",
                }
            elif data["data"]["qrCodeStatus"] == "EXPIRED":
                return {"code": -1, "status": "error", "msg": "二维码无效或已过期"}
            elif data["data"]["qrCodeStatus"] == "CANCELED":
                return {"code": -1, "status": "error", "msg": "用户取消登录"}
            elif data["data"]["qrCodeStatus"] == "SCANED":
                return {"code": 0, "status": "scanned", "msg": "请在手机上确认"}
            else:
                return {"code": 0, "status": "waiting", "msg": "等待扫码"}
        except Exception as e:
            return {"code": -1, "msg": f"检查状态时出错: {e}"}

    @staticmethod
    def redirect_url(
        request: Request,
        pickcode: str = "",
        file_name: str = "",
        id: int = 0,
        share_code: str = "",
        receive_code: str = "",
    ):
        """
        115网盘302跳转
        """
        user_agent = request.headers.get("User-Agent") or b""
        logger.debug(f"【302跳转服务】获取到客户端UA: {user_agent}")

        if share_code:
            try:
                if not receive_code:
                    receive_code = servicer.redirect.get_receive_code(share_code)
                elif len(receive_code) != 4:
                    return f"Bad receive_code: {receive_code}"
                if not id:
                    if file_name:
                        id = servicer.redirect.share_get_id_for_name(
                            share_code,
                            receive_code,
                            file_name,
                        )
                if not id:
                    return f"Please specify id or name: share_code={share_code!r}"
                url = servicer.redirect.get_share_downurl(
                    share_code, receive_code, id, user_agent
                )
                logger.info(f"【302跳转服务】获取 115 下载地址成功: {url}")
            except Exception as e:
                logger.error(f"【302跳转服务】获取 115 下载地址失败: {e}")
                return f"获取 115 下载地址失败: {e}"
        else:
            if not pickcode:
                logger.debug("【302跳转服务】Missing pickcode parameter")
                return "Missing pickcode parameter"

            if not (len(pickcode) == 17 and pickcode.isalnum()):
                logger.debug(f"【302跳转服务】Bad pickcode: {pickcode} {file_name}")
                return f"Bad pickcode: {pickcode} {file_name}"

            try:
                if configer.get_config("link_redirect_mode") == "cookie":
                    url = servicer.redirect.get_downurl_cookie(
                        pickcode.lower(), user_agent
                    )
                else:
                    url = servicer.redirect.get_downurl_open(
                        pickcode.lower(), user_agent
                    )
                logger.info(
                    f"【302跳转服务】获取 115 下载地址成功: {url} {url['file_name']}"  # pylint: disable=E1126
                )
            except Exception as e:
                logger.error(f"【302跳转服务】获取 115 下载地址失败: {e}")
                return f"获取 115 下载地址失败: {e}"

        return Response(
            status_code=302,
            headers={
                "Location": url,
                "Content-Disposition": f'attachment; filename="{quote(url["file_name"])}"',
            },
            media_type="application/json; charset=utf-8",
            content=dumps({"status": "redirecting", "url": url}),
        )

    @staticmethod
    def trigger_full_sync_api(self) -> Dict:
        """
        触发全量同步
        """
        try:
            if not configer.get_config("enabled") or not configer.get_config("cookies"):
                return {"code": 1, "msg": "插件未启用或未配置cookie"}

            servicer.start_full_sync()

            return {"code": 0, "msg": "全量同步任务已启动"}
        except Exception as e:
            return {"code": 1, "msg": f"启动全量同步任务失败: {str(e)}"}

    @staticmethod
    def trigger_full_sync_db_api() -> Dict:
        """
        触发全量同步数据库
        """
        try:
            if not configer.get_config("enabled") or not configer.get_config("cookies"):
                return {"code": 1, "msg": "插件未启用或未配置cookie"}

            servicer.start_full_sync_db()

            return {"code": 0, "msg": "全量同步数据库任务已启动"}
        except Exception as e:
            return {"code": 1, "msg": f"启动全量同步数据库任务失败: {str(e)}"}

    @staticmethod
    def trigger_share_sync_api() -> Dict:
        """
        触发分享同步
        """
        try:
            if not configer.get_config("enabled") or not configer.get_config("cookies"):
                return {"code": 1, "msg": "插件未启用或未配置cookie"}

            if not configer.get_config("user_share_link") and not (
                configer.get_config("user_share_code")
                and configer.get_config("user_receive_code")
            ):
                return {"code": 1, "msg": "未配置分享链接或分享码"}

            servicer.start_share_sync()

            return {"code": 0, "msg": "分享同步任务已启动"}
        except Exception as e:
            return {"code": 1, "msg": f"启动分享同步任务失败: {str(e)}"}

    @staticmethod
    def get_status_api() -> Dict:
        """
        获取插件状态
        """
        return {
            "code": 0,
            "data": {
                "enabled": configer.get_config("enabled"),
                "has_client": bool(servicer.client),
                "running": (
                    bool(servicer.scheduler.get_jobs()) if servicer.scheduler else False
                )
                or bool(
                    servicer.monitor_life_thread
                    and servicer.monitor_life_thread.is_alive()
                )
                or bool(servicer.service_observer),
            },
        }

    @staticmethod
    def add_transfer_share(share_url: str = "") -> Dict:
        """
        添加分享转存整理
        """
        if not configer.get_config("pan_transfer_enabled") or not configer.get_config(
            "pan_transfer_paths"
        ):
            return {
                "code": -1,
                "error": "配置错误",
                "message": "用户未配置网盘整理",
            }

        if not share_url:
            return {
                "code": -1,
                "error": "参数错误",
                "message": "未传入分享链接",
            }

        data = servicer.sharetransferhelper.share_url_extract(share_url)
        share_code = data["share_code"]
        receive_code = data["receive_code"]
        logger.info(
            f"【分享转存API】解析分享链接 share_code={share_code} receive_code={receive_code}"
        )
        if not share_code or not receive_code:
            logger.error(f"【分享转存API】解析分享链接失败：{share_url}")
            return {
                "code": -1,
                "error": "解析失败",
                "message": "解析分享链接失败",
            }

        file_mediainfo = servicer.sharetransferhelper.add_share_recognize_mediainfo(
            share_code=share_code, receive_code=receive_code
        )

        parent_path = configer.get_config("pan_transfer_paths").split("\n")[0]
        parent_id = idpathcacher.get_id_by_dir(directory=str(parent_path))
        if not parent_id:
            parent_id = servicer.client.fs_dir_getid(parent_path)["id"]
            logger.info(f"【分享转存API】获取到转存目录 ID：{parent_id}")
            idpathcacher.add_cache(id=int(parent_id), directory=str(parent_path))

        payload = {
            "share_code": share_code,
            "receive_code": receive_code,
            "file_id": 0,
            "cid": int(parent_id),
            "is_check": 0,
        }
        resp = servicer.client.share_receive(payload)
        if resp["state"]:
            logger.info(f"【分享转存API】转存 {share_code} 到 {parent_path} 成功！")
            if configer.get_config("notify"):
                if not file_mediainfo:
                    post_message(
                        mtype=NotificationType.Plugin,
                        title=i18n.translate("share_add_success"),
                        text=f"""
分享链接：https://115cdn.com/s/{share_code}?password={receive_code}
转存目录：{parent_path}
""",
                    )
                else:
                    post_message(
                        mtype=NotificationType.Plugin,
                        title=i18n.translate(
                            "share_add_success_2",
                            title=file_mediainfo.title,
                            year=file_mediainfo.year,
                        ),
                        text=f"""
链接：https://115cdn.com/s/{share_code}?password={receive_code}
简介：{file_mediainfo.overview}
""",
                        image=file_mediainfo.poster_path,
                    )
            servicer.sharetransferhelper.post_share_info(
                "115", share_code, receive_code, file_mediainfo
            )
            return {
                "code": 0,
                "success": True,
                "message": "转存成功",
                "data": {
                    "media_info": asdict(file_mediainfo) if file_mediainfo else None,
                    "save_parent": {"path": parent_path, "id": parent_id},
                },
                "timestamp": datetime.now().isoformat(),
            }

        logger.info(f"【分享转存API】转存 {share_code} 失败：{resp['error']}")
        return {
            "code": -1,
            "error": "转存失败",
            "message": resp["error"],
        }

    @staticmethod
    def offline_tasks_api(payload: Dict) -> Dict:
        """
        离线任务列表
        """
        page = int(payload.get("page", 1))
        limit = int(payload.get("limit", 10))

        all_tasks = servicer.offlinehelper.get_cached_data()
        total = len(all_tasks)

        if limit == -1:
            paginated_tasks = all_tasks
        else:
            start = (page - 1) * limit
            end = start + limit
            paginated_tasks = all_tasks[start:end]

        response = {
            "code": 0,
            "msg": "获取离线任务成功",
            "data": {"total": total, "tasks": paginated_tasks},
        }

        return response

    @staticmethod
    def add_offline_task_api(payload: Dict) -> Dict:
        """
        添加离线下载任务
        """
        links = payload.get("links")
        path = payload.get("path")

        if not path:
            status = servicer.offlinehelper.add_urls_to_transfer(links)
        else:
            status = servicer.offlinehelper.add_urls_to_path(links, path)

        if status:
            return {
                "code": 0,
                "msg": f"{len(links)} 个新任务已成功添加，正在后台处理。",
                "data": "",
            }
        return {
            "code": -1,
            "msg": "添加失败：请前往后台查看插件日志",
            "data": "",
        }

    @staticmethod
    def check_feature_api(name: str = "") -> Dict:
        """
        判断是否有权限使用此增强功能
        """
        return OOPServerHelper.check_feature(name)

    @staticmethod
    def get_webdav_status_api() -> Dict:
        """
        获取WebDAV服务状态
        """
        status = webdav_service.get_status()
        return {
            "code": 0,
            "msg": "获取WebDAV状态成功",
            "data": status
        }

    @staticmethod
    def start_webdav_service_api() -> Dict:
        """
        启动WebDAV服务
        """
        if webdav_service.start():
            return {
                "code": 0,
                "msg": "WebDAV服务启动成功",
                "data": webdav_service.get_status()
            }
        else:
            return {
                "code": -1,
                "msg": "WebDAV服务启动失败",
                "data": None
            }

    @staticmethod
    def stop_webdav_service_api() -> Dict:
        """
        停止WebDAV服务
        """
        if webdav_service.stop():
            return {
                "code": 0,
                "msg": "WebDAV服务停止成功",
                "data": webdav_service.get_status()
            }
        else:
            return {
                "code": -1,
                "msg": "WebDAV服务停止失败",
                "data": None
            }

    @staticmethod
    def restart_webdav_service_api() -> Dict:
        """
        重启WebDAV服务
        """
        if webdav_service.restart():
            return {
                "code": 0,
                "msg": "WebDAV服务重启成功",
                "data": webdav_service.get_status()
            }
        else:
            return {
                "code": -1,
                "msg": "WebDAV服务重启失败",
                "data": None
            }
