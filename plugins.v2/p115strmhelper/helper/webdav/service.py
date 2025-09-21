import os
import signal
from socket import socket, AF_INET, SOCK_STREAM
from time import sleep
from pathlib import Path
from typing import Optional

from multiprocessing import Process
from waitress import serve

from app.log import logger

from .app import create_hybrid_webdav_app
from ...core.config import configer
from ...schemas.webdav import WebDAVStatus


def run_server_process(host, port, local_path_str):
    """
    这个函数将在一个独立的子进程中运行
    """
    try:
        logger.info(f"[WebDAV-Process pid={os.getpid()}] Starting...")
        app = create_hybrid_webdav_app(local_path_str)
        serve(app, host=host, port=port, threads=16)
    except KeyboardInterrupt:
        logger.info(f"[WebDAV-Process pid={os.getpid()}] Received stop signal.")
    except Exception as e:
        logger.error(
            f"[WebDAV-Process pid={os.getpid()}] Server crashed: {e}", exc_info=True
        )
        raise


class WebDAVService:
    """
    WebDAV服务管理器
    """

    def __init__(self):
        self.server_process: Optional[Process] = None
        self.is_running = False

    def start(self) -> bool:
        """
        在一个新的子进程中启动WebDAV服务
        """
        if self.is_running:
            logger.info("【WebDAV】服务已在运行中")
            return True

        if not configer.webdav_enabled:
            logger.info("【WebDAV】服务未启用")
            return False
        if not configer.webdav_local_mapping_path:
            logger.error("【WebDAV】未配置本地映射路径")
            return False
        if WebDAVService._is_port_in_use():
            logger.error(f"【WebDAV】端口 {configer.webdav_port} 已被占用")
            return False
        local_path = Path(configer.webdav_local_mapping_path)
        try:
            local_path.mkdir(parents=True, exist_ok=True)
            if not os.access(local_path, os.R_OK | os.W_OK):
                logger.error(f"【WebDAV】本地映射目录权限不足: {local_path}")
                return False
        except Exception as e:
            logger.error(f"【WebDAV】创建本地映射目录失败: {e}")
            return False

        try:
            self.server_process = Process(
                target=run_server_process,
                args=(
                    configer.webdav_host,
                    configer.webdav_port,
                    str(local_path),
                ),
                daemon=True,
                name="WebDAV-Server-Process",
            )
            self.server_process.start()

            sleep(2)

            if self.server_process.is_alive() and WebDAVService._is_port_in_use():
                self.is_running = True
                logger.info(
                    f"【WebDAV】服务已在子进程 (PID: {self.server_process.pid}) 中启动: http://{configer.webdav_host}:{configer.webdav_port}"
                )
                return True
            else:
                logger.error("【WebDAV】服务启动失败或子进程立即退出")
                if self.server_process.is_alive():
                    self.server_process.terminate()
                self.server_process = None
                return False

        except Exception as e:
            logger.error(f"【WebDAV】启动失败: {e}", exc_info=True)
            return False

    def stop(self, force=False) -> bool:
        """
        停止WebDAV服务子进程
        """
        if not self.is_running or not self.server_process:
            self.is_running = False
            return True

        logger.info(f"【WebDAV】正在停止服务进程 (PID: {self.server_process.pid})...")
        try:
            if not self.server_process.is_alive():
                logger.warning("【WebDAV】服务器进程已经不存在")
                self.is_running = False
                self.server_process = None
                return True

            if not force:
                self.server_process.terminate()
                self.server_process.join(timeout=5)

            if force or self.server_process.is_alive():
                logger.warning(
                    "【WebDAV】服务器进程未能在5秒内终止，现在强制杀死 (SIGKILL)..."
                )
                try:
                    os.kill(self.server_process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.server_process.join(timeout=2)

            if self.server_process.is_alive():
                logger.error("【WebDAV】无法终止服务器进程！")
            else:
                logger.info("【WebDAV】服务已成功停止")

            return not self.server_process.is_alive()

        except Exception as e:
            logger.error(f"【WebDAV】停止服务时发生错误: {e}", exc_info=True)
            return False
        finally:
            self.is_running = False
            self.server_process = None

    def restart(self) -> bool:
        """
        重启WebDAV服务
        """
        logger.info("【WebDAV】正在重启服务...")
        self.stop()
        sleep(2)
        return self.start()

    @staticmethod
    def _is_port_in_use() -> bool:
        """
        检查端口是否被占用
        """
        try:
            sock = socket(AF_INET, SOCK_STREAM)
            result = sock.connect_ex((configer.webdav_host, configer.webdav_port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def get_status(self) -> WebDAVStatus:
        """
        获取服务状态
        """
        return WebDAVStatus(
            enabled=configer.webdav_enabled,
            running=self.is_running,
            host=configer.webdav_host,
            port=configer.webdav_port,
            local_mapping_path=configer.webdav_local_mapping_path,
            url=f"http://{configer.webdav_host}:{configer.webdav_port}"
            if self.is_running
            else None,
            auth_enabled=bool(configer.webdav_username and configer.webdav_password),
            username=configer.webdav_username if configer.webdav_username else None,
            process_alive=(
                self.server_process.is_alive() if self.server_process else False
            ),
            pid=self.server_process.pid if self.server_process else None,
        )


webdav_service = WebDAVService()
