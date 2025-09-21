from typing import List, Optional

from pydantic import BaseModel, Field


class OfflineTasksPayload(BaseModel):
    """
    离线任务列表请求体
    """
    page: int = Field(default=1, ge=1, description="页码，必须大于等于1")
    limit: int = Field(default=10, description="每页数量，-1 表示获取所有")

class AddOfflineTaskPayload(BaseModel):
    """
    添加离线下载任务请求体
    """
    links: List[str] = Field(..., description="下载链接列表，不能为空")
    path: Optional[str] = Field(default=None, description="指定的下载路径（可选）")

class OfflineTaskItem(BaseModel):
    """
    离线下载任务列表
    """
    info_hash: str
    name: str
    size: int
    size_text: str
    status: int
    status_text: str
    percent: float
    add_time: int

class OfflineTasksData(BaseModel):
    """
    返回数据
    """
    total: int
    tasks: List[OfflineTaskItem]
