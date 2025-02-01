from sqlalchemy import Column, String, Integer, Sequence
from sqlalchemy.orm import Session

from ...db_manager import db_update, db_query, CloudTerminatorBase


class U115StrmFiles(CloudTerminatorBase):
    # ID
    id = Column(Integer, Sequence('id'), primary_key=True, index=True)
    # 文件路径
    file_path = Column(String, primary_key=True, index=True)
    # 文件内容
    content = Column(String)

    @staticmethod
    @db_query
    def get_by_path(db: Session, file_path: str):
        return db.query(U115StrmFiles).filter(U115StrmFiles.file_path == file_path).first()

    @staticmethod
    @db_query
    def get_by_id(db: Session, file_id: int):
        return db.query(U115StrmFiles).filter(U115StrmFiles.id == file_id).first()

    @db_update
    def delete_by_path(self, db: Session, file_path: str):
        data = self.get_by_path(db, file_path)
        if data:
            data.delete(db, data.id)
        return True

    @db_update
    def delete_by_id(self, db: Session, file_id: int):
        data = self.get_by_id(db, file_id)
        if data:
            data.delete(db, data.id)
        return True

