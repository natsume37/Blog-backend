from fastapi import APIRouter, Depends, HTTPException, Query
from qiniu import Auth
from app.core.config import get_settings, Settings
from app.core.deps import get_current_admin, get_current_user, get_current_user_optional
from app.schemas.common import ResponseModel
import hashlib
import time
import urllib.parse

router = APIRouter(prefix="/upload", tags=["上传"])

# URL签名密钥（用于前后端加密验证）
URL_SIGN_SECRET = "martin_blog_2024_secret_key"


def generate_signed_key(key: str, timestamp: int) -> str:
    """生成资源key的签名"""
    raw_str = f"{key}-{timestamp}-{URL_SIGN_SECRET}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()


def verify_signed_key(key: str, timestamp: int, sign: str) -> bool:
    """验证签名"""
    expected = generate_signed_key(key, timestamp)
    return sign == expected


def generate_qiniu_timestamp_url(base_url: str, key: str, timestamp_key: str, expire_seconds: int = 3600) -> str:
    """
    生成七牛云时间戳防盗链URL
    
    算法说明:
    - key: 七牛云控制台配置的时间戳防盗链密钥
    - path: URL中的路径部分（不含querystring）
    - T: 过期时间的16进制小写形式
    - 签名原始字符串 S = key + url_encode(path) + T
    - 签名 SIGN = md5(S).to_lower()
    - 最终URL: 原始URL + &sign=<SIGN>&t=<T> (如果有querystring) 或 ?sign=<SIGN>&t=<T>
    
    Args:
        base_url: 原始URL (如 http://xxx.com/path/file.mp4 或 http://xxx.com/path/file.mp4?v=1)
        key: 资源key (路径部分，如 /path/file.mp4)
        timestamp_key: 七牛云时间戳防盗链密钥
        expire_seconds: 过期时间（秒），默认3600秒
    
    Returns:
        带签名的URL
    """
    # 计算过期时间戳并转为16进制小写
    expire_time = int(time.time()) + expire_seconds
    t = format(expire_time, 'x')  # 转为16进制小写
    
    # 构建路径部分（需要确保以 / 开头）
    path = f"/{key}" if not key.startswith('/') else key
    
    # URL编码路径（斜线不参与编码）
    # 对路径的每个部分分别编码，然后用 / 连接
    path_parts = path.split('/')
    encoded_parts = [urllib.parse.quote(part, safe='') for part in path_parts]
    encoded_path = '/'.join(encoded_parts)
    
    # 生成签名: md5(key + url_encode(path) + T).to_lower()
    sign_str = f"{timestamp_key}{encoded_path}{t}"
    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()
    
    # 组装最终URL
    if '?' in base_url:
        return f"{base_url}&sign={sign}&t={t}"
    else:
        return f"{base_url}?sign={sign}&t={t}"


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
    支持时间戳防盗链模式（通过配置开启）
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

    base_url = f"{settings.QINIU_DOMAIN}/{key}"
    expire_seconds = settings.QINIU_TIMESTAMP_EXPIRE if settings.is_qiniu_timestamp_enabled else 3600
    
    # 根据配置选择签名方式
    if settings.is_qiniu_timestamp_enabled:
        # 使用七牛云时间戳防盗链
        private_url = generate_qiniu_timestamp_url(
            base_url=base_url,
            key=key,
            timestamp_key=settings.QINIU_TIMESTAMP_KEY,
            expire_seconds=expire_seconds
        )
    else:
        # 使用七牛云私有空间签名（原方式）
        q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
        private_url = q.private_download_url(base_url, expires=expire_seconds)
    
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
            "expires": timestamp + expire_seconds  # 过期时间戳
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

    base_url = f"{settings.QINIU_DOMAIN}/{key}"
    expire_seconds = settings.QINIU_TIMESTAMP_EXPIRE if settings.is_qiniu_timestamp_enabled else 3600
    
    # 根据配置选择签名方式
    if settings.is_qiniu_timestamp_enabled:
        # 使用七牛云时间戳防盗链
        private_url = generate_qiniu_timestamp_url(
            base_url=base_url,
            key=key,
            timestamp_key=settings.QINIU_TIMESTAMP_KEY,
            expire_seconds=expire_seconds
        )
    else:
        # 使用七牛云私有空间签名（原方式）
        q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
        private_url = q.private_download_url(base_url, expires=expire_seconds)
    
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

    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    expire_seconds = settings.QINIU_TIMESTAMP_EXPIRE if settings.is_qiniu_timestamp_enabled else 3600
    
    result = {}
    timestamp = int(time.time())
    
    # 根据配置选择签名方式
    if settings.is_qiniu_timestamp_enabled:
        # 使用七牛云时间戳防盗链
        for key in key_list:
            base_url = f"{settings.QINIU_DOMAIN}/{key}"
            private_url = generate_qiniu_timestamp_url(
                base_url=base_url,
                key=key,
                timestamp_key=settings.QINIU_TIMESTAMP_KEY,
                expire_seconds=expire_seconds
            )
            sign = generate_signed_key(key, timestamp)
            
            result[key] = {
                "url": private_url,
                "timestamp": timestamp,
                "sign": sign,
                "expires": timestamp + expire_seconds
            }
    else:
        # 使用七牛云私有空间签名（原方式）
        q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
        for key in key_list:
            base_url = f"{settings.QINIU_DOMAIN}/{key}"
            private_url = q.private_download_url(base_url, expires=expire_seconds)
            sign = generate_signed_key(key, timestamp)
            
            result[key] = {
                "url": private_url,
                "timestamp": timestamp,
                "sign": sign,
                "expires": timestamp + expire_seconds
            }
    
    return ResponseModel(
        code=200,
        data=result
    )
