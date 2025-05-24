from pathlib import Path
from typing import Any, Generator, Self, List

from sqlalchemy import create_engine, and_, inspect
from sqlalchemy.orm import (
    as_declarative,
    declared_attr,
    sessionmaker,
    scoped_session,
    Session,
)

from app.core.config import settings
from app.db import get_args_db, update_args_db


class __DBManager:
    """
    数据库管理器，
    """

    # 数据库引擎
    Engine = None
    # 会话工厂
    SessionFactory = None
    # 多线程全局使用的数据库会话
    ScopedSession = None

    def init_database(self, db_path: Path):
        """
        初始化数据库引擎
        """
        db_kwargs = {
            "url": f"sqlite:///{db_path}",
            "pool_pre_ping": settings.DB_POOL_PRE_PING,
            "echo": settings.DB_ECHO,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }
        self.Engine = create_engine(**db_kwargs)
        self.SessionFactory = sessionmaker(bind=self.Engine)
        self.ScopedSession = scoped_session(self.SessionFactory)

    def close_database(self):
        """
        关闭所有数据库连接并清理资源
        """
        if self.Engine:
            self.Engine.dispose()
        self.Engine = None
        self.SessionFactory = None
        self.ScopedSession = None

    def is_initialized(self) -> bool:
        """
        判断数据库是否初始化并连接、创建会话工厂
        """
        if (
            self.Engine is None
            or self.SessionFactory is None
            or self.ScopedSession is None
        ):
            return False
        return True


def get_db() -> Generator:
    """
    获取数据库会话，用于WEB请求
    :return: Session
    """
    db = None
    try:
        db = ct_db_manager.SessionFactory()
        yield db
    finally:
        if db:
            db.close()


def db_update(func):
    """
    数据库更新类操作装饰器，第一个参数必须是数据库会话或存在db参数
    """

    def wrapper(*args, **kwargs):
        # 是否关闭数据库会话
        _close_db = False
        # 从参数中获取数据库会话
        db = get_args_db(args, kwargs)
        if not db:
            # 如果没有获取到数据库会话，创建一个
            db = ct_db_manager.ScopedSession()
            # 标记需要关闭数据库会话
            _close_db = True
            # 更新参数中的数据库会话
            args, kwargs = update_args_db(args, kwargs, db)
        try:
            # 执行函数
            result = func(*args, **kwargs)
            # 提交事务
            db.commit()
        except Exception as err:
            # 回滚事务
            db.rollback()
            raise err
        finally:
            # 关闭数据库会话
            if _close_db:
                db.close()
        return result

    return wrapper


def db_query(func):
    """
    数据库查询操作装饰器，第一个参数必须是数据库会话或存在db参数
    注意：db.query列表数据时，需要转换为list返回
    """

    def wrapper(*args, **kwargs):
        # 是否关闭数据库会话
        _close_db = False
        # 从参数中获取数据库会话
        db = get_args_db(args, kwargs)
        if not db:
            # 如果没有获取到数据库会话，创建一个
            db = ct_db_manager.ScopedSession()
            # 标记需要关闭数据库会话
            _close_db = True
            # 更新参数中的数据库会话
            args, kwargs = update_args_db(args, kwargs, db)
        try:
            # 执行函数
            result = func(*args, **kwargs)
        except Exception as err:
            raise err
        finally:
            # 关闭数据库会话
            if _close_db:
                db.close()
        return result

    return wrapper


@as_declarative()
class P115StrmHelperBase:
    id: Any
    __name__: str

    @db_update
    def create(self, db: Session):
        db.add(self)

    @classmethod
    @db_query
    def get(cls, db: Session, rid: int) -> Self:
        return db.query(cls).filter(and_(cls.id == rid)).first()

    @db_update
    def update(self, db: Session, payload: dict):
        payload = {k: v for k, v in payload.items() if v is not None}
        for key, value in payload.items():
            setattr(self, key, value)
        if inspect(self).detached:
            db.add(self)

    @classmethod
    @db_update
    def delete(cls, db: Session, rid):
        db.query(cls).filter(and_(cls.id == rid)).delete()

    @classmethod
    @db_update
    def truncate(cls, db: Session):
        db.query(cls).delete()

    @classmethod
    @db_query
    def list(cls, db: Session) -> List[Self]:
        result = db.query(cls).all()
        return list(result)

    def to_dict(self):
        return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}  # noqa

    @declared_attr
    def __tablename__(self) -> str:
        return self.__name__.lower()


class DbOper:
    """
    数据库操作基类
    """

    def __init__(self, db: Session = None):
        self._db = db or ct_db_manager.ScopedSession()

    def __del__(self):
        # 确保在对象销毁时关闭 Session
        if hasattr(self, "_db") and self._db:
            self._db.close()


# 全局数据库会话
ct_db_manager = __DBManager()
