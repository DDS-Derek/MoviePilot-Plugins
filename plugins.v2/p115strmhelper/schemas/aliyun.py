from typing import Optional

from pydantic import BaseModel


class AliyunDriveQRCodeData(BaseModel):
    qrcode: str
    t: str
    ck: str


class CheckAliyunDriveQRCodeParams(BaseModel):
    t: str
    ck: str


class CheckAliyunDriveQRCodeData(BaseModel):
    status: str
    msg: str
    token: Optional[str] = None
