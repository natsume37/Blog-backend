from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
import logging

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserInfo, Token, UserUpdate, ForgotPasswordRequest, ResetPasswordRequest, UserRegister
from app.schemas.common import ResponseModel
from app.core.cache import RedisClient
from app.core.email import send_reset_password_email, send_register_verification_email
import random
import string

router = APIRouter(prefix="/auth", tags=["认证"])
logger = logging.getLogger(__name__)

# 随机头像生成函数
def generate_random_avatar() -> str:
    """生成随机头像URL，使用 DiceBear API"""
    styles = ['adventurer', 'avataaars', 'bottts', 'fun-emoji', 'lorelei', 'micah', 'miniavs', 'personas', 'pixel-art']
    style = random.choice(styles)
    seed = random.randint(1, 100000)
    return f"https://api.dicebear.com/7.x/{style}/svg?seed={seed}"


@router.post("/login", response_model=ResponseModel[Token])
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        logger.warning(f"Login failed for user: {user_data.username}")
        return ResponseModel(code=401, msg="用户名或密码错误")
    
    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user_data.username}")
        return ResponseModel(code=403, msg="账号已被禁用")
    
    # Create token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    logger.info(f"User logged in: {user.username}")
    
    user_info = UserInfo(
        id=user.id,
        username=user.username,
        nickname=user.nickname or user.username,
        avatar=user.avatar,
        email=user.email,
        intro=user.intro,
        is_admin=user.is_admin,
        created_at=user.created_at
    )
    
    return ResponseModel(
        code=200,
        data=Token(token=access_token, userInfo=user_info),
        msg="登录成功"
    )


@router.get("/me", response_model=ResponseModel[UserInfo])
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息 (验证 token 是否有效)"""
    return ResponseModel(
        code=200,
        data=UserInfo(
            id=current_user.id,
            username=current_user.username,
            nickname=current_user.nickname or current_user.username,
            avatar=current_user.avatar,
            email=current_user.email,
            intro=current_user.intro,
            is_admin=current_user.is_admin,
            created_at=current_user.created_at
        )
    )


@router.post("/register/send-code", response_model=ResponseModel)
def send_register_code(
    request: ForgotPasswordRequest,  # 复用 ForgotPasswordRequest (只包含 email)
    db: Session = Depends(get_db)
):
    """发送注册验证码"""
    # Check if email exists
    if db.query(User).filter(User.email == request.email).first():
        return ResponseModel(code=400, msg="该邮箱已被注册")
    
    # 生成6位验证码
    code = ''.join(random.choices(string.digits, k=6))
    
    # 存入 Redis，有效期 10 分钟
    redis_client = RedisClient()
    key = f"register_code:{request.email}"
    redis_client.set(key, code, expire=600)
    
    # 发送邮件
    if send_register_verification_email(request.email, code):
        return ResponseModel(code=200, msg="验证码已发送至您的邮箱")
    else:
        return ResponseModel(code=500, msg="邮件发送失败，请稍后重试")


@router.post("/register", response_model=ResponseModel)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """用户注册"""
    # Verify code
    redis_client = RedisClient()
    key = f"register_code:{user_data.email}"
    saved_code = redis_client.get(key)
    
    if not saved_code or saved_code != user_data.code:
        return ResponseModel(code=400, msg="验证码无效或已过期")

    # Check if username exists
    if db.query(User).filter(User.username == user_data.username).first():
        return ResponseModel(code=400, msg="用户名已存在")
    
    # Check if email exists
    if db.query(User).filter(User.email == user_data.email).first():
        return ResponseModel(code=400, msg="邮箱已被注册")
    
    # Create user with random avatar
    hashed_password = get_password_hash(user_data.password)
    random_avatar = generate_random_avatar()
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        nickname=user_data.username,
        avatar=random_avatar,
        is_active=True,
        is_admin=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Delete code
    redis_client.client.delete(key)
    
    return ResponseModel(code=200, msg="注册成功")


@router.put("/profile", response_model=ResponseModel[UserInfo])
def update_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新用户个人信息"""
    # 更新非空字段
    if user_data.nickname is not None:
        current_user.nickname = user_data.nickname
    if user_data.avatar is not None:
        current_user.avatar = user_data.avatar
    if user_data.intro is not None:
        current_user.intro = user_data.intro
    if user_data.email is not None:
        # 检查邮箱是否被其他用户使用
        existing_user = db.query(User).filter(
            User.email == user_data.email, 
            User.id != current_user.id
        ).first()
        if existing_user:
            return ResponseModel(code=400, msg="该邮箱已被其他用户使用")
        current_user.email = user_data.email
    
    db.commit()
    db.refresh(current_user)
    
    return ResponseModel(
        code=200,
        data=UserInfo(
            id=current_user.id,
            username=current_user.username,
            nickname=current_user.nickname or current_user.username,
            avatar=current_user.avatar or "",
            email=current_user.email,
            intro=current_user.intro or "",
            is_admin=current_user.is_admin,
            created_at=current_user.created_at
        ),
        msg="更新成功"
    )


@router.post("/forgot-password", response_model=ResponseModel)
def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """忘记密码 - 发送验证码"""
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        # 为了安全，即使邮箱不存在也提示发送成功，防止枚举邮箱
        # 但在开发阶段，为了方便调试，可以返回真实信息，或者这里我们选择返回成功但不实际发送
        # 实际上，为了用户体验，通常会提示邮箱未注册
        return ResponseModel(code=404, msg="该邮箱未注册")
    
    # 生成6位验证码
    code = ''.join(random.choices(string.digits, k=6))
    
    # 存入 Redis，有效期 10 分钟
    redis_client = RedisClient()
    key = f"reset_password_code:{request.email}"
    redis_client.set(key, code, expire=600)
    
    # 发送邮件
    if send_reset_password_email(request.email, code):
        return ResponseModel(code=200, msg="验证码已发送至您的邮箱")
    else:
        return ResponseModel(code=500, msg="邮件发送失败，请稍后重试")


@router.post("/reset-password", response_model=ResponseModel)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """重置密码"""
    # 验证验证码
    redis_client = RedisClient()
    key = f"reset_password_code:{request.email}"
    saved_code = redis_client.get(key)
    
    if not saved_code or saved_code != request.code:
        return ResponseModel(code=400, msg="验证码无效或已过期")
    
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        return ResponseModel(code=404, msg="用户不存在")
    
    # 更新密码
    user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    
    # 删除验证码
    redis_client.client.delete(key)
    
    return ResponseModel(code=200, msg="密码重置成功，请重新登录")
