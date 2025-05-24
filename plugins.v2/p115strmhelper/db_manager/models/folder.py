from sqlalchemy import Column, Integer, String, Text

from ...db_manager import P115StrmHelperBase


class Folder(P115StrmHelperBase):
    """
    文件夹类
    """

    __tablename__ = "folders"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    path = Column(Text, nullable=False)
