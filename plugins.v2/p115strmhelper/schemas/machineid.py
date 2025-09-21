from typing import Optional

from pydantic import BaseModel


class MachineID(BaseModel):
    """
    machine id 数据
    """
    machine_id: str

class MachineIDFeature(BaseModel):
    """
    增强功能权限
    """
    machine_id: Optional[str] = None
    feature_name: Optional[str] = None
    enabled: bool = False
