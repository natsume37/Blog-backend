from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """Standard API response model"""
    code: int = 200
    data: Optional[T] = None
    msg: str = "success"


class PagedData(BaseModel, Generic[T]):
    """Paginated data model"""
    records: List[T]
    total: int
    current: int
    size: int


class PagedResponseModel(BaseModel, Generic[T]):
    """Paginated response model"""
    code: int = 200
    data: Optional[PagedData[T]] = None
    msg: str = "success"
