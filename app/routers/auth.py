from fastapi import APIRouter, Depends, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
import logging
import json
import re
import secrets
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request as UrlRequest, urlopen

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, decode_access_token
from app.core.config import settings
from app.core.deps import get_current_user, require_public_interactions_enabled
from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.user import UserCreate, UserLogin, UserInfo, Token, UserUpdate, ForgotPasswordRequest, ResetPasswordRequest, UserRegister
from app.schemas.common import ResponseModel
from app.core.cache import RedisClient
from app.core.email import send_reset_password_email, send_register_verification_email
import random
import string

router = APIRouter(prefix="/auth", tags=["认证"])
logger = logging.getLogger(__name__)

GITHUB_STATE_COOKIE = "github_oauth_state"
GITHUB_STATE_COOKIE_PATH = f"{settings.API_V1_PREFIX}/auth"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


def _get_client_ip(request: Request) -> str:
    header_candidates = [
        request.headers.get("x-forwarded-for"),
        request.headers.get("x-real-ip"),
        request.headers.get("cf-connecting-ip"),
    ]
    for value in header_candidates:
        if not value:
            continue
        first = value.split(",")[0].strip()
        if first and first.lower() != "unknown":
            return first
    return request.client.host if request.client else ""


def _record_login_log(
    db: Session,
    request: Request,
    username: str,
    success: bool,
    reason: str = "",
    user_id: int | None = None,
) -> None:
    try:
        db.add(LoginLog(
            user_id=user_id,
            username=(username or "")[:64],
            ip=_get_client_ip(request)[:50],
            user_agent=request.headers.get("user-agent", "")[:500],
            success=success,
            reason=reason[:255],
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Record login log failed: %s", e)


def _set_auth_cookie(response: Response, access_token: str) -> None:
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _user_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        username=user.username,
        nickname=user.nickname or user.username,
        avatar=user.avatar or "",
        email=user.email,
        intro=user.intro or "",
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


def _safe_frontend_path(value: str | None) -> str:
    if not value:
        return "/"
    path = value.strip()
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    if "\r" in path or "\n" in path:
        return "/"
    return path


def _frontend_url(path: str) -> str:
    safe_path = _safe_frontend_path(path)
    base = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
    if not base:
        return safe_path
    return f"{base}{safe_path}"


def _github_callback_url(request: Request) -> str:
    configured = (settings.GITHUB_REDIRECT_URI or "").strip()
    if configured:
        return configured
    return str(request.url_for("github_oauth_callback"))


def _github_failure_redirect(message: str) -> RedirectResponse:
    url = _frontend_url(f"/login?github_error={quote(message)}")
    response = RedirectResponse(url=url, status_code=303)
    response.delete_cookie(key=GITHUB_STATE_COOKIE, path=GITHUB_STATE_COOKIE_PATH)
    return response


def _http_json(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> dict[str, Any] | list[dict[str, Any]]:
    payload = None
    request_headers = headers.copy() if headers else {}
    if data is not None:
        payload = urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request_headers.setdefault("Accept", "application/json")
    request = UrlRequest(url, data=payload, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("GitHub request failed") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub returned invalid JSON") from exc
    if not isinstance(parsed, (dict, list)):
        raise RuntimeError("GitHub returned unexpected response")
    return parsed


def _primary_verified_email(emails: list[dict[str, Any]]) -> str | None:
    for item in emails:
        if item.get("primary") and item.get("verified") and item.get("email"):
            return str(item["email"])
    for item in emails:
        if item.get("verified") and item.get("email"):
            return str(item["email"])
    return None


def _fallback_github_email(github_id: str) -> str:
    return f"github-{github_id}@users.noreply.github.local"


def _unique_github_email(db: Session, github_id: str, preferred: str | None) -> str:
    candidate = preferred if preferred and len(preferred) <= 100 else None
    if candidate and not db.query(User).filter(User.email == candidate).first():
        return candidate
    fallback = _fallback_github_email(github_id)
    if not db.query(User).filter(User.email == fallback).first():
        return fallback
    return f"github-{github_id}-{secrets.token_hex(3)}@users.noreply.github.local"


def _unique_username(db: Session, login: str | None, github_id: str) -> str:
    raw = (login or f"github_{github_id}").strip().lower()
    slug = re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")
    if not slug:
        slug = f"github_{github_id}"
    if not slug.startswith("github_"):
        slug = f"github_{slug}"
    base = slug[:42].rstrip("_") or f"github_{github_id}"
    for index in range(100):
        suffix = "" if index == 0 else f"_{index}"
        candidate = f"{base[:50 - len(suffix)]}{suffix}"
        if not db.query(User).filter(User.username == candidate).first():
            return candidate
    return f"github_{github_id}_{secrets.token_hex(3)}"[:50]


def _get_or_create_github_user(
    db: Session,
    github_user: dict[str, Any],
    verified_email: str | None,
    *,
    allow_create: bool = True,
) -> User:
    github_id = str(github_user.get("id") or "").strip()
    if not github_id:
        raise ValueError("GitHub user id missing")

    login = str(github_user.get("login") or "").strip()
    avatar = str(github_user.get("avatar_url") or "").strip()
    display_name = str(github_user.get("name") or login or "").strip()
    public_email = str(github_user.get("email") or "").strip() or None

    user = db.query(User).filter(User.github_id == github_id).first()
    if user is None and verified_email:
        user = db.query(User).filter(User.email == verified_email).first()
        if user is not None:
            if user.github_id and user.github_id != github_id:
                raise ValueError("GitHub email already linked to another account")
            user.github_id = github_id

    if user is None:
        if not allow_create:
            raise PermissionError("Owner-only mode does not create GitHub users")
        email = _unique_github_email(db, github_id, verified_email or public_email)
        user = User(
            username=_unique_username(db, login, github_id),
            email=email,
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
            nickname=(display_name or login or "GitHub User")[:50],
            avatar=avatar[:500],
            intro="",
            github_id=github_id,
            github_login=login[:100],
            is_active=True,
            is_admin=False,
        )
        db.add(user)
    else:
        user.github_login = login[:100]
        if not user.avatar and avatar:
            user.avatar = avatar[:500]
        if not user.nickname and display_name:
            user.nickname = display_name[:50]

    db.commit()
    db.refresh(user)
    return user

# 随机头像生成函数
def generate_random_avatar() -> str:
    """生成随机头像URL，使用 DiceBear API"""
    styles = ['adventurer', 'avataaars', 'bottts', 'fun-emoji', 'lorelei', 'micah', 'miniavs', 'personas', 'pixel-art']
    style = random.choice(styles)
    seed = random.randint(1, 100000)
    return f"https://api.dicebear.com/7.x/{style}/svg?seed={seed}"


@router.post("/login", response_model=ResponseModel[Token])
def login(user_data: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        logger.warning(f"Login failed for user: {user_data.username}")
        _record_login_log(db, request, user_data.username, False, "用户名或密码错误")
        return ResponseModel(code=401, msg="用户名或密码错误")
    
    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user_data.username}")
        _record_login_log(db, request, user.username, False, "账号已被禁用", user.id)
        return ResponseModel(code=403, msg="账号已被禁用")

    if settings.OWNER_ONLY_MODE and not user.is_admin:
        logger.warning("Owner-only login rejected for user: %s", user.username)
        _record_login_log(db, request, user.username, False, "仅允许站长登录", user.id)
        return ResponseModel(code=403, msg="这里只允许站长登录")
    
    # Create token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    logger.info(f"User logged in: {user.username}")
    _record_login_log(db, request, user.username, True, "登录成功", user.id)

    _set_auth_cookie(response, access_token)
    user_info = _user_info(user)
    
    return ResponseModel(
        code=200,
        data=Token(token=access_token, userInfo=user_info),
        msg="登录成功"
    )


@router.get("/github/authorize")
def github_oauth_authorize(request: Request, redirect: str = "/"):
    """跳转到 GitHub OAuth 授权页"""
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        return _github_failure_redirect("GitHub 登录未配置")

    redirect_path = _safe_frontend_path(redirect)
    nonce = secrets.token_urlsafe(24)
    state = create_access_token(
        data={"nonce": nonce, "redirect": redirect_path},
        expires_delta=timedelta(minutes=10),
    )
    query = urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": _github_callback_url(request),
        "scope": settings.GITHUB_OAUTH_SCOPE,
        "state": state,
        "allow_signup": "true",
    })
    response = RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{query}", status_code=303)
    response.set_cookie(
        key=GITHUB_STATE_COOKIE,
        value=nonce,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=600,
        path=GITHUB_STATE_COOKIE_PATH,
    )
    return response


@router.get("/github/callback", name="github_oauth_callback")
def github_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """处理 GitHub OAuth 回调并写入站点登录 Cookie"""
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        return _github_failure_redirect("GitHub 登录未配置")
    if not code or not state:
        _record_login_log(db, request, "github", False, "GitHub 回调参数缺失")
        return _github_failure_redirect("GitHub 登录参数无效")

    state_payload = decode_access_token(state)
    expected_nonce = request.cookies.get(GITHUB_STATE_COOKIE)
    if not state_payload or state_payload.get("nonce") != expected_nonce:
        _record_login_log(db, request, "github", False, "GitHub state 校验失败")
        return _github_failure_redirect("GitHub 登录状态已失效，请重试")
    redirect_path = _safe_frontend_path(str(state_payload.get("redirect") or "/"))

    try:
        token_response = _http_json(
            GITHUB_TOKEN_URL,
            method="POST",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": _github_callback_url(request),
            },
        )
        if not isinstance(token_response, dict) or not token_response.get("access_token"):
            raise RuntimeError("GitHub token missing")
        github_token = str(token_response["access_token"])
        auth_headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        github_user = _http_json(GITHUB_USER_URL, headers=auth_headers)
        if not isinstance(github_user, dict):
            raise RuntimeError("GitHub user missing")
        try:
            github_emails = _http_json(GITHUB_EMAILS_URL, headers=auth_headers)
        except RuntimeError:
            github_emails = []
        verified_email = _primary_verified_email(github_emails if isinstance(github_emails, list) else [])
        user = _get_or_create_github_user(
            db,
            github_user,
            verified_email,
            allow_create=not settings.OWNER_ONLY_MODE,
        )
    except Exception as exc:
        logger.warning("GitHub OAuth login failed: %s", exc)
        _record_login_log(db, request, "github", False, "GitHub 登录失败")
        return _github_failure_redirect("GitHub 登录失败，请稍后重试")

    if settings.OWNER_ONLY_MODE and not user.is_admin:
        _record_login_log(db, request, user.username, False, "仅允许站长登录", user.id)
        return _github_failure_redirect("这里只允许站长登录")

    if not user.is_active:
        _record_login_log(db, request, user.username, False, "账号已被禁用", user.id)
        return _github_failure_redirect("账号已被禁用")

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response = RedirectResponse(url=_frontend_url(redirect_path), status_code=303)
    _set_auth_cookie(response, access_token)
    response.delete_cookie(key=GITHUB_STATE_COOKIE, path=GITHUB_STATE_COOKIE_PATH)
    _record_login_log(db, request, user.username, True, "GitHub 登录成功", user.id)
    return response


@router.post("/logout", response_model=ResponseModel)
def logout(response: Response):
    """退出登录"""
    response.delete_cookie(key="access_token", path="/")
    return ResponseModel(code=200, msg="退出成功")


@router.get("/me", response_model=ResponseModel[UserInfo])
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息 (验证 token 是否有效)"""
    return ResponseModel(
        code=200,
        data=_user_info(current_user),
    )


@router.post("/register/send-code", response_model=ResponseModel)
def send_register_code(
    request: ForgotPasswordRequest,  # 复用 ForgotPasswordRequest (只包含 email)
    db: Session = Depends(get_db),
    _: None = Depends(require_public_interactions_enabled),
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
def register(
    user_data: UserRegister,
    db: Session = Depends(get_db),
    _: None = Depends(require_public_interactions_enabled),
):
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
        data=_user_info(current_user),
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
        # 防止通过接口枚举邮箱
        return ResponseModel(code=200, msg="验证码已发送至您的邮箱")
    
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
