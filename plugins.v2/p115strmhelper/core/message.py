from typing import Optional

from app.chain import ChainBase
from app.core.config import settings
from app.schemas import Notification, NotificationType, MessageChannel

from .config import configer


class PluginChian(ChainBase):
    """
    插件处理链
    """

    pass


def post_message(
    channel: MessageChannel = None,
    mtype: NotificationType = None,
    title: Optional[str] = None,
    text: Optional[str] = None,
    image: Optional[str] = None,
    link: Optional[str] = None,
    userid: Optional[str] = None,
    username: Optional[str] = None,
    **kwargs,
):
    """
    发送消息
    """
    chain = PluginChian()
    if not link:
        link = settings.MP_DOMAIN(
            f"#/plugins?tab=installed&id={configer.get_config('PLUSIN_NAME')}"
        )
    chain.post_message(
        Notification(
            channel=channel,
            mtype=mtype,
            title=title,
            text=text,
            image=image,
            link=link,
            userid=userid,
            username=username,
            **kwargs,
        )
    )
