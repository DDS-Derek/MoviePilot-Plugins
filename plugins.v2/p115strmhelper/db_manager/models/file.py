from sqlalchemy import Column, Integer, String, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base

from ...db_manager import P115StrmHelperBase


class File(P115StrmHelperBase):
    """
    文件类
    """

    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, nullable=False)
    name = Column(String(255), default="")
    sha1 = Column(String(40), default="")
    size = Column(BigInteger, default=0)
    pickcode = Column(String(50), default="")
    ctime = Column(BigInteger, default=0)
    mtime = Column(BigInteger, default=0)
    path = Column(Text, default="")
    extra = Column(Text)
