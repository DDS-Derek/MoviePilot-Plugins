from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError

from ..db_manager import P115StrmHelperBase

# 显式载入，确保表单模型已注册
from ..db_manager.models import *


def init_db(engine):
    """
    初始化数据库
    """
    if not engine:
        raise SQLAlchemyError("数据库引擎获取失败")
    # 全量建表
    P115StrmHelperBase.metadata.create_all(engine)


def update_db(db_path, database_dir):
    """
    更新数据库
    """
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(database_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    upgrade(alembic_cfg, "head")
