from typing import List, Dict

import requests

from app.log import logger
from app.core.config import settings

from .framework.registry import command_registry, view_registry
from .framework.callbacks import Action
from .framework.handler import BaseActionHandler
from .session import Session
from ..core.config import configer

command_registry.clear()


class ActionHandler(BaseActionHandler):
    """
    动作处理器
    处理用户的动作请求，并执行相应的业务逻辑
    """

    @command_registry.command(name="go_to", code="gt")
    def handle_go_to(self, session: Session, action: Action):
        """
        处理跳转到指定视图的操作
        """
        if action.view:
            if view_registry.get_by_name(action.view):
                session.go_to(action.view)
                if action.view == "search":
                    # 如果跳转到 start 视图，重置业务逻辑
                    session.business = session.business.__class__()
            else:
                raise ValueError(f"未知视图 '{action.view}'，跳转失败。")

    @command_registry.command(name="go_back", code="gb")
    def handle_go_back(self, session: Session, action: Action):
        """
        处理返回操作
        """
        if action.view:
            if view_registry.get_by_name(action.view):
                session.go_back(action.view)
                if action.view == "search":
                    # 如果返回到 start 视图，重置业务逻辑
                    session.business = session.business.__class__()
            else:
                logger.warning(f"未知视图 '{action.view}'，尝试返回失败。")
                raise ValueError(f"未知视图 '{action.view}'，返回失败。")

    @command_registry.command(name="page_next", code="pn")
    def handle_page_next(self, session: Session, _: Action):
        """
        处理下一页操作
        """
        session.page_next()

    @command_registry.command(name="page_prev", code="pp")
    def handle_page_prev(self, session: Session, _: Action):
        """
        处理上一页操作
        """
        session.page_prev()

    @command_registry.command(name="close", code="cl")
    def handle_closed(self, session: Session, _: Action):
        """
        处理关闭操作
        """
        session.view.name = "close"

    @command_registry.command(name="refresh", code="rf")
    def handle_refresh(self, session: Session, _: Action):
        """
        处理刷新操作
        """
        session.refresh_view()

    @command_registry.command(name="search", code="sr")
    def handle_search(self, session: Session, action: Action):
        """
        处理搜索操作
        """
        if action.value is None:
            raise ValueError("搜索关键词不能为空。")
        search_keyword = action.value.strip()
        session.business.search_keyword = search_keyword

    @command_registry.command(name="resource", code="rs")
    def handle_resource(self, session: Session, action: Action):
        """
        处理资源操作
        """
        if action.value is None:
            raise ValueError("搜索关键词不能为空。")
        resource_key = action.value
        session.business.resource_key = resource_key
        if not configer.get_config("nullbr_app_id") or not configer.get_config(
            "nullbr_api_key"
        ):
            session.business.resource_key = 0
            session.business.resource_key_list = [
                {
                    "name": resource_key,
                }
            ]
        session.view.refresh = True
        session.go_to("resource_list")

    @command_registry.command(name="subscribe", code="sb")
    def handle_select_subscribe(
        self, session: Session, action: Action
    ) -> List[Dict] | None:
        """
        处理选中资源的操作
        """
        try:
            if action.value is None:
                raise ValueError("value 不能为空。")
            # 索引号
            item_index = int(action.value)
            # 全部搜索数据
            search_data = session.business.resource_info.get("data", [])

            if not search_data:
                raise ValueError("当前没有可用的资源。")
            if 0 <= item_index < len(search_data):
                data = search_data[item_index]
                resp = requests.get(
                    f"{configer.get_config('moviepilot_address').rstrip('/')}/api/v1/plugin/P115StrmHelper/add_transfer_share?apikey={settings.API_TOKEN}&share_url={data.get('shareurl')}"
                )
                if resp.json().get("code") == 0:
                    session.go_to("subscribe_success")
                else:
                    session.go_to("subscribe_fail")
            else:
                raise IndexError("索引超出范围。")
        except (ValueError, IndexError, TypeError) as e:
            logger.error(
                f"处理 subscribe 失败: value={action.value}, error={e}", exc_info=True
            )
            session.go_to("start")
            return [{"type": "error_message", "text": "选择资源时发生错误，请重试。"}]
        return None
