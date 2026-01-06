from fastapi import APIRouter, Depends, HTTPException, Query
from qiniu import Auth
from app.core.config import Settings
from app.core.deps import get_current_admin, get_current_user, get_current_user_optional
from app.schemas.common import ResponseModel
from functools import lru_cache
import hashlib
import time
import urllib.parse

router = APIRouter(prefix="/upload", tags=["上传"])

# URL签名密钥（用于前后端加密验证）
URL_SIGN_SECRET = "martin_blog_2024_secret_key"

@lru_cache()
def get_settings():
    return Settings()


def generate_signed_key(key: str, timestamp: int) -> str:
    """生成资源key的签名"""
    raw_str = f"{key}-{timestamp}-{URL_SIGN_SECRET}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()


def verify_signed_key(key: str, timestamp: int, sign: str) -> bool:
    """验证签名"""
    expected = generate_signed_key(key, timestamp)
    return sign == expected


@router.get("/token", response_model=ResponseModel)
def get_upload_token(
    current_user = Depends(get_current_admin), # Only admin can upload
    settings: Settings = Depends(get_settings)
):
    """获取七牛云上传凭证"""
    if not settings.is_qiniu_enabled:
        raise HTTPException(status_code=501, detail="图床服务未配置，无法上传文件")

    q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    
    # 策略：只允许上传到指定 bucket，有效时间 3600s
    # return_body 定义了七牛云回调或者直接返回给前端的数据格式
    policy = {
        'returnBody': '{"key":"$(key)","hash":"$(etag)","fsize":$(fsize),"bucket":"$(bucket)","name":"$(x:name)"}'
    }
    
    token = q.upload_token(settings.QINIU_BUCKET, None, 3600, policy)
    
    return ResponseModel(
        code=200,
        data={
            "token": token,
            "domain": settings.QINIU_DOMAIN
        }
    )


@router.get("/private-url", response_model=ResponseModel)
def get_private_download_url(
    key: str,
    current_user = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings)
):
    """
    获取七牛云私有空间下载链接
    返回带签名的私有链接，每次请求都会生成新的签名URL
    """
    if not settings.is_qiniu_enabled:
        # 如果未配置，尝试直接返回原始key作为URL（假定是完整URL）或者报错
        # 这里为了前端兼容性，返回原始key，虽然可能无法访问
        return ResponseModel(
            code=200,
            data={
                "url": key, # Fallback
                "key": key,
                "timestamp": int(time.time()),
                "sign": "",
                "expires": 0
            }
        )

    q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    
    # 构建私有链接，有效期 1 小时
    base_url = f"{settings.QINIU_DOMAIN}/{key}"
    private_url = q.private_download_url(base_url, expires=3600)
    
    # 生成时间戳和签名（用于前端验证和防盗链）
    timestamp = int(time.time())
    sign = generate_signed_key(key, timestamp)
    
    return ResponseModel(
        code=200,
        data={
            "url": private_url,
            "key": key,
            "timestamp": timestamp,
            "sign": sign,
            "expires": timestamp + 3600  # 过期时间戳
        }
    )


@router.get("/signed-url", response_model=ResponseModel)
def get_signed_url(
    key: str = Query(..., description="资源key"),
    t: int = Query(..., description="时间戳"),
    sign: str = Query(..., description="签名"),
    settings: Settings = Depends(get_settings)
):
    """
    通过加密链接获取真实的七牛云私有URL
    前端请求时会带上加密参数，后端验证后返回真实可访问的URL
    这样外露的链接每次都不同（因为时间戳不同），且无法直接看到真实的key
    """
    # 验证签名是否有效
    if not verify_signed_key(key, t, sign):
        raise HTTPException(status_code=403, detail="签名验证失败")
    
    # 检查时间戳是否过期（允许1小时的有效期）
    current_time = int(time.time())
    if current_time - t > 3600:
        raise HTTPException(status_code=403, detail="链接已过期")
    
    if not settings.is_qiniu_enabled:
        raise HTTPException(status_code=501, detail="图床服务未配置")

    q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    
    # 构建新的私有链接
    base_url = f"{settings.QINIU_DOMAIN}/{key}"
    private_url = q.private_download_url(base_url, expires=3600)
    
    return ResponseModel(
        code=200,
        data={"url": private_url}
    )


@router.get("/encrypt-key", response_model=ResponseModel)
def encrypt_resource_key(
    key: str = Query(..., description="资源key"),
    current_user = Depends(get_current_user_optional)
):
    """
    加密资源key，返回加密后的参数
    用于生成每次不同的外露链接
    """
    timestamp = int(time.time())
    sign = generate_signed_key(key, timestamp)
    
    # 返回加密后的参数，前端可以用这些参数构建加密链接
    return ResponseModel(
        code=200,
        data={
            "key": key,
            "t": timestamp,
            "sign": sign,
            "expires": timestamp + 3600
        }
    )


@router.get("/batch-private-urls", response_model=ResponseModel)
def get_batch_private_urls(
    keys: str = Query(..., description="资源keys，用逗号分隔"),
    current_user = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings)
):
    """
    批量获取七牛云私有空间下载链接
    减少多次请求的开销
    """
    if not settings.is_qiniu_enabled:
        # Fallback: return keys as urls
        key_list = [k.strip() for k in keys.split(",") if k.strip()]
        timestamp = int(time.time())
        result = {}
        for key in key_list:
             result[key] = {
                "url": key,
                "timestamp": timestamp,
                "sign": "",
                "expires": 0
            }
        return ResponseModel(code=200, data=result)

    q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    
    result = {}
    timestamp = int(time.time())
    
    for key in key_list:
        base_url = f"{settings.QINIU_DOMAIN}/{key}"
        private_url = q.private_download_url(base_url, expires=3600)
        sign = generate_signed_key(key, timestamp)
        
        result[key] = {
            "url": private_url,
            "timestamp": timestamp,
            "sign": sign,
            "expires": timestamp + 3600
        }
    
    return ResponseModel(
        code=200,
        data=result
    )
