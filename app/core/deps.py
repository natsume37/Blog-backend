from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import logging

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

logger = logging.getLogger(__name__)



oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    request: Request = None,
    token: Optional[str] = Depends(oauth2_scheme_optional)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    raw_token = token or (request.cookies.get("access_token") if request else None)
    if not raw_token:
        raise credentials_exception

    payload = decode_access_token(raw_token)
    if payload is None:
        raise credentials_exception
        
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
        
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id_int).first()
    if user is None:
        raise credentials_exception
        
    return user


def get_optional_current_user(
    db: Session = Depends(get_db),
    request: Request = None,
    token: Optional[str] = Depends(oauth2_scheme_optional)
) -> Optional[User]:
    """获取当前用户（可选，未登录返回 None）"""
    raw_token = token or (request.cookies.get("access_token") if request else None)
    if not raw_token:
        return None
    
    payload = decode_access_token(raw_token)
    if payload is None:
        return None
        
    user_id: str = payload.get("sub")
    if user_id is None:
        return None
        
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return None

    user = db.query(User).filter(User.id == user_id_int).first()
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# 别名，方便使用
get_current_user_optional = get_optional_current_user


def get_current_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if not current_user.is_admin:
        logger.warning(f"User {current_user.username} attempted to access admin area without privileges")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The user doesn't have enough privileges"
        )
    return current_user
