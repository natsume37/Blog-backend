from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    nickname: str
    avatar: str
    email: str
    intro: str = ""
    is_admin: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    token: str
    userInfo: UserInfo


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    intro: Optional[str] = None
    email: Optional[EmailStr] = None


# 管理员创建用户
class UserAdminCreate(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None
    nickname: Optional[str] = None
    is_admin: bool = False


# 管理员更新用户
class UserAdminUpdate(BaseModel):
    nickname: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
