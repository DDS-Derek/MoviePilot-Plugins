from typing import TypeVar, Generic, Optional
from pydantic.generics import GenericModel


T = TypeVar("T")


class ApiResponse(GenericModel, Generic[T]):
    code: int = 0
    msg: str = "success"
    data: Optional[T] = None
