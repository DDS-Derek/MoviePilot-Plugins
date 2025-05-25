from typing import Dict, List

from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.orm import Session

from ...db_manager import db_update, db_query, P115StrmHelperBase


class Folder(P115StrmHelperBase):
    """
    文件夹类
    """

    __tablename__ = "folders"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    path = Column(Text, nullable=False)

    @staticmethod
    @db_query
    def get_by_path(db: Session, file_path: str):
        """
        通过路径获取
        """
        return db.execute(
            select(Folder).where(Folder.path == file_path)
        ).scalar_one_or_none()

    @staticmethod
    @db_query
    def get_by_id(db: Session, file_id: int):
        """
        通过ID获取
        """
        return db.scalars(select(Folder).where(Folder.id == file_id)).first()

    @staticmethod
    @db_query
    def get_by_parent_id(db: Session, parent_id: int):
        """
        通过parent_id获取
        """
        return (
            db.execute(select(Folder).where(Folder.parent_id == parent_id))
            .scalars()
            .all()
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
            if entry["table"] == "folders":
                db.merge(Folder(**entry["data"]))
        db.commit()
        return True

    @staticmethod
    @db_update
    def remove_by_path_batch(db: Session, path: str):
        """
        通过路径批量删除
        """
        db.query(Folder).filter(Folder.path.startswith(path)).delete(
            synchronize_session=False
        )
        return True
