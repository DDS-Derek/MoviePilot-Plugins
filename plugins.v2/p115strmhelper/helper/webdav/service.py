import os
import threading
import time
from pathlib import Path
from typing import Optional

from wsgiref.simple_server import make_server, WSGIServer
from wsgidav.wsgidav_app import WsgiDAVApp

from app.log import logger
from ...core.config import configer
from .hybrid_app import create_hybrid_webdav_app


class WebDAVService:
    """
    WebDAV服务管理器
    """

    def __init__(self):
        self.server: Optional[WSGIServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self) -> bool:
        """
        启动WebDAV服务
        """
        if not configer.webdav_enabled:
            logger.info("【WebDAV】服务未启用")
            return False

        if not configer.webdav_local_mapping_path:
            logger.error("【WebDAV】未配置本地映射路径")
            return False

        # 确保本地映射目录存在
        local_path = Path(configer.webdav_local_mapping_path)
        local_path.mkdir(parents=True, exist_ok=True)

        try:
            # 创建WebDAV应用
            app = create_hybrid_webdav_app(str(local_path))

            # 创建服务器
            self.server = make_server(
                configer.webdav_host, configer.webdav_port, app, server_class=WSGIServer
            )

            # 启动服务器线程
            self.server_thread = threading.Thread(
                target=self._run_server, daemon=True, name="WebDAV-Server"
            )
            self.server_thread.start()

            self.is_running = True
            logger.info(
                f"【WebDAV】服务已启动: http://{configer.webdav_host}:{configer.webdav_port}"
            )
            return True

        except Exception as e:
            logger.error(f"【WebDAV】启动失败: {e}")
            return False

    def stop(self) -> bool:
        """
        停止WebDAV服务
        """
        if not self.is_running or not self.server:
            return True

        try:
            self.server.shutdown()
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5)

            self.is_running = False
            logger.info("【WebDAV】服务已停止")
            return True

        except Exception as e:
            logger.error(f"【WebDAV】停止失败: {e}")
            return False

    def restart(self) -> bool:
        """
        重启WebDAV服务
        """
        logger.info("【WebDAV】正在重启服务...")
        self.stop()
        time.sleep(1)
        return self.start()

    def _run_server(self):
        """
        运行服务器
        """
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"【WebDAV】服务器运行错误: {e}")
            self.is_running = False

    def get_status(self) -> dict:
        """
        获取服务状态
        """
        return {
            "enabled": configer.webdav_enabled,
            "running": self.is_running,
            "host": configer.webdav_host,
            "port": configer.webdav_port,
            "local_mapping_path": configer.webdav_local_mapping_path,
            "url": f"http://{configer.webdav_host}:{configer.webdav_port}"
            if self.is_running
            else None,
        }


# 全局WebDAV服务实例
webdav_service = WebDAVService()
