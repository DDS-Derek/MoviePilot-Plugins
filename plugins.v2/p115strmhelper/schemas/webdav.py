from typing import Optional
from pydantic import BaseModel


class WebDAVStatus(BaseModel):
    """
    WebDAV服务状态模型
    """
    enabled: bool
    running: bool
    host: str
    port: int
    local_mapping_path: Optional[str]
    url: Optional[str]
    auth_enabled: bool
    username: Optional[str]
    process_alive: bool
    pid: Optional[int]


class WebDavApi(BaseModel):
    """
    WebDav服务API返回
    """
    code: int = 0
    msg: Optional[str] = None
    data: Optional[WebDAVStatus] = None
