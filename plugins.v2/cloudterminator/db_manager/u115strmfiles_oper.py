from . import DbOper
from .models.u115_strm import U115StrmFiles


class U115StrmFilesOper(DbOper):
    """
    115 网盘 strm 操作管理
    """

    def add(self, **kwargs):
        """
        新增 strm 文件
        """
        data = U115StrmFiles(**kwargs)
        data.create(self._db)

    def get_by_path(self, file_path: str) -> U115StrmFiles:
        """
        根据文件路径获取 strm 文件
        """
        return U115StrmFiles.get_by_path(self._db, file_path)

    def get_by_id(self, file_id: int) -> U115StrmFiles:
        """
        根据文件 ID 获取 strm 文件
        """
        return U115StrmFiles.get_by_id(self._db, file_id)

    def update_by_path(self, file_path: str, payload: dict):
        """
        根据文件路径更新 strm 文件
        """
        data = self.get_by_path(file_path)
        if data:
            data.update(self._db, payload)
        return True

    def update_by_id(self, file_id: int, payload: dict):
        """
        根据文件 ID 更新 strm 文件
        """
        data = self.get_by_id(file_id)
        if data:
            data.update(self._db, payload)
        return True

    def delete_by_path(self, file_path: str):
        """
        根据文件路径删除 strm 文件
        """
        return U115StrmFiles.delete_by_path(self._db, file_path)

    def delete_by_id(self, file_id: int):
        """
        根据文件 ID 删除 strm 文件
        """
        return U115StrmFiles.delete_by_id(self._db, file_id)

    def get_all(self):
        """
        获取所有 strm 文件
        """
        return U115StrmFiles.list(self._db)
