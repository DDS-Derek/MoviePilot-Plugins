from typing import List

from pydantic import BaseModel


class BrowseDirParams(BaseModel):
    path: str = "/"
    is_local: bool = False


class DirectoryItem(BaseModel):
    name: str
    path: str
    is_dir: bool


class BrowseDirData(BaseModel):
    path: str
    items: List[DirectoryItem]
