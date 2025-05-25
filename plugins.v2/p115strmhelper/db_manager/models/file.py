from typing import Dict, List

from sqlalchemy import Column, Integer, String, Text, BigInteger, select
from sqlalchemy.orm import Session

from ...db_manager import db_update, db_query, P115StrmHelperBase


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

    @staticmethod
    @db_query
    def get_by_path(db: Session, file_path: str):
        """
        通过路径获取
        """
        return db.execute(
            select(File).where(File.path == file_path)
        ).scalar_one_or_none()

    @staticmethod
    @db_query
    def get_by_id(db: Session, file_id: int):
        """
        通过ID获取
        """
        return db.scalars(select(File).where(File.id == file_id)).first()

    @staticmethod
    @db_query
    def get_by_parent_id(db: Session, parent_id: int):
        """
        通过parent_id获取
        """
        return (
            db.execute(select(File).where(File.parent_id == parent_id)).scalars().all()
        )

    @db_update
    def delete_by_path(self, db: Session, file_path: str):
        """
        通过路径删除
        """
        data = self.get_by_path(db, file_path)
        if data:
            data.delete(db, data.id)
        return True

    @db_update
    def delete_by_id(self, db: Session, file_id: int):
        """
        通过ID删除
        """
        data = self.get_by_id(db, file_id)
        if data:
            data.delete(db, data.id)
        return True

    @staticmethod
    @db_update
    def upsert_batch(db: Session, batch: List[Dict]):
        """
        批量写入或更新数据
        """
        for entry in batch:
            if entry["table"] == "files":
                db.merge(File(**entry["data"]))
        return True

    @staticmethod
    @db_update
    def remove_by_path_batch(db: Session, path: str):
        """
        通过路径批量删除
        """
        db.query(File).filter(File.path.startswith(path)).delete(
            synchronize_session=False
        )
        return True
