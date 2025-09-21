from typing import Optional

from pydantic import BaseModel


class GetQRCodeParams(BaseModel):
    client_type: str = "alipaymini"


class QRCodeData(BaseModel):
    uid: str
    time: str
    sign: str
    qrcode: str
    tips: str
    client_type: str


class CheckQRCodeParams(BaseModel):
    uid: str
    time: str
    sign: str
    client_type: str = "alipaymini"


class CheckQRCodeData(BaseModel):
    status: str
    msg: str
    cookie: Optional[str] = None


class UserInfo(BaseModel):
    name: Optional[str]
    is_vip: Optional[bool]
    is_forever_vip: Optional[bool]
    vip_expire_date: Optional[str]
    avatar: Optional[str]


class StorageInfo(BaseModel):
    total: Optional[str]
    used: Optional[str]
    remaining: Optional[str]


class UserStorageStatusResponse(BaseModel):
    success: bool
    error_message: Optional[str] = None
    user_info: Optional[UserInfo]
    storage_info: Optional[StorageInfo]
