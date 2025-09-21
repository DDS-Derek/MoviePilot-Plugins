from pydantic import BaseModel


class PluginStatusData(BaseModel):
    enabled: bool
    has_client: bool
    running: bool
