from typing import Dict, Optional, List

from . import DbOper
from .models.folder import Folder
from .models.file import File
from sqlalchemy import select


class DatabaseHelper(DbOper):
    """
    数据库操作
    """

    def process_item(self, item: Dict) -> List[Dict]:
        """处理单个项目，分离文件夹和文件数据"""
        results = []
        ancestors = item.get("ancestors", [])

        # 处理祖先文件夹
        for i, ancestor in enumerate(ancestors[1:-1], start=1):
            path = "/" + "/".join(a["name"] for a in ancestors[1 : i + 1])
            results.append(
                {
                    "table": "folders",
                    "data": {
                        "id": ancestor["id"],
                        "parent_id": ancestor["parent_id"],
                        "name": ancestor["name"],
                        "path": path,
                    },
                }
            )

        # 处理文件本身
        results.append(
            {
                "table": "files",
                "data": {
                    "id": item["id"],
                    "parent_id": item["parent_id"],
                    "name": item["name"],
                    "sha1": item.get("sha1", ""),
                    "size": item.get("size", 0),
                    "pickcode": item.get("pickcode", item.get("pick_code", "")),
                    "ctime": item.get("ctime", 0),
                    "mtime": item.get("mtime", 0),
                    "path": item.get("path", ""),
                    "extra": str(item) if item else None,
                },
            }
        )

        return results

    def upsert_batch(self, batch: List[Dict]):
        """批量写入或更新数据"""
        session = self._db
        try:
            for entry in batch:
                model = Folder if entry["table"] == "folders" else File
                session.merge(model(**entry["data"]))
            session.commit()
        except Exception as e:
            session.rollback()
            raise e

    def get_by_path(self, path: str) -> Optional[Dict]:
        """通过路径获取项目"""
        session = self._db
        try:
            # 先查文件
            file = session.execute(
                select(File).where(File.path == path)
            ).scalar_one_or_none()

            if file:
                return {
                    **file.__dict__,
                    "type": "file",
                    # 移除内部属性
                    "_sa_instance_state": None,
                }

            # 再查文件夹
            folder = session.execute(
                select(Folder).where(Folder.path == path)
            ).scalar_one_or_none()

            if folder:
                return {**folder.__dict__, "type": "folder", "_sa_instance_state": None}

            return None
        except Exception as e:
            self._db.rollback()
            raise e

    def get_children(self, path: str) -> Dict:
        """获取路径下的所有子项"""
        session = self._db
        try:
            # 获取父文件夹ID
            parent = session.execute(
                select(Folder).where(Folder.path == path)
            ).scalar_one_or_none()

            if not parent:
                return {"files": [], "subfolders": []}

            parent_id = parent.id

            # 查询子文件
            files = (
                session.execute(select(File).where(File.parent_id == parent_id))
                .scalars()
                .all()
            )

            # 查询子文件夹
            subfolders = (
                session.execute(select(Folder).where(Folder.parent_id == parent_id))
                .scalars()
                .all()
            )

            # 转换为字典并清理内部属性
            def clean_record(record):
                d = record.__dict__
                d.pop("_sa_instance_state", None)
                d["type"] = "file" if isinstance(record, File) else "folder"
                return d

            return {
                "files": [clean_record(f) for f in files],
                "subfolders": [clean_record(sf) for sf in subfolders],
                "meta": {
                    "parent_path": path,
                    "parent_id": parent_id,
                    "total_count": len(files) + len(subfolders),
                },
            }
        except Exception as e:
            self._db.rollback()
            raise e
