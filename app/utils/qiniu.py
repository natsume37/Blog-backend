import hashlib
import time
import urllib.parse
import re
from typing import Optional

# URL签名密钥（用于前后端加密验证）
# 如果需要更高安全性，建议移入 app/core/config.py 或环境变量
URL_SIGN_SECRET = "martin_blog_2024_secret_key"

def generate_signed_key(key: str, timestamp: int) -> str:
    """生成资源key的签名 (用于前端直传后的验证)"""
    raw_str = f"{key}-{timestamp}-{URL_SIGN_SECRET}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

def verify_signed_key(key: str, timestamp: int, sign: str) -> bool:
    """验证签名"""
    expected = generate_signed_key(key, timestamp)
    return sign == expected

def generate_qiniu_timestamp_url(base_url: str, key: str, timestamp_key: str, expire_seconds: int = 3600) -> str:
    """
    生成七牛云时间戳防盗链URL
    """
    try:
        # 计算过期时间戳并转为16进制小写
        expire_time = int(time.time()) + expire_seconds
        t = format(expire_time, 'x')  # 转为16进制小写
        
        # 构建路径部分（需要确保以 / 开头）
        path = f"/{key}" if not key.startswith('/') else key
        
        # URL编码路径（斜线不参与编码）
        path_parts = path.split('/')
        encoded_parts = [urllib.parse.quote(part, safe='') for part in path_parts]
        encoded_path = '/'.join(encoded_parts)
        
        # 生成签名: md5(key + url_encode(path) + T).to_lower()
        sign_str = f"{timestamp_key}{encoded_path}{t}"
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()
        
        # 组装最终URL
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}sign={sign}&t={t}"
    except Exception as e:
        print(f"Error generating qiniu url: {e}")
        return base_url

def strip_qiniu_params(content: str, qiniu_domain: str) -> str:
    """
    去除内容中七牛云链接的签名参数 (sign, t)
    用于保存到数据库前清洗数据
    
    Args:
        content: 文章内容或URL字符串
        qiniu_domain: 七牛云域名 (如 http://cdn.example.com)
    
    Returns:
        清洗后的内容
    """
    if not content or not qiniu_domain:
        return content
        
    # 提取域名（去掉协议头部分以防万一）
    domain = qiniu_domain.replace("http://", "").replace("https://", "")
    
    # 正则逻辑：
    # 匹配包含该域名的URL，并替换掉 ?sign=...&t=... 或 &sign=... 等参数
    # 简单起见，我们主要处理 md 链接 `(url)` 和 img 标签 `src="url"` 中的 URL
    # 但由于 markdown 内容复杂，直接针对 URL 模式进行替换更稳妥
    
    def replacer(match):
        full_url = match.group(0)
        
        try:
            # 解析 URL
            parsed = urllib.parse.urlparse(full_url)
            
            # 解析查询参数
            query_params = urllib.parse.parse_qs(parsed.query)
            
            # 移除 sign 和 t
            if 'sign' in query_params:
                del query_params['sign']
            if 't' in query_params:
                del query_params['t']
            
            # 重组查询字符串
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            
            # 重组 URL
            new_url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            
            return new_url
        except:
            return full_url

    # 构造正则：http(s)://domain... 直到遇到 空格、引号、括号、换行等结束符
    # 注意转义域名中的点号
    escaped_domain = re.escape(domain)
    pattern = rf"https?://{escaped_domain}[^\s\"')\]]*"
    
    return re.sub(pattern, replacer, content)

def refresh_qiniu_params_in_content(content: str, qiniu_domain: str, timestamp_key: str, expire_seconds: int = 3600) -> str:
    """
    刷新内容中七牛云链接的签名 (读取时使用)
    """
    if not content or not qiniu_domain or not timestamp_key:
        return content
        
    domain = qiniu_domain.replace("http://", "").replace("https://", "")
    
    def replacer(match):
        full_url = match.group(0)
        
        try:
            # 1. 先清洗现有 URL (去掉旧的 sign 和 t)
            # 解析 URL
            parsed = urllib.parse.urlparse(full_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            
            if 'sign' in query_params:
                del query_params['sign']
            if 't' in query_params:
                del query_params['t']
                
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            clean_url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            
            # 2. 提取 Key (path部分，去掉开头的 /)
            key = parsed.path.lstrip('/')
            if not key:
                return full_url
                
            # 3. 生成新签名
            return generate_qiniu_timestamp_url(clean_url, key, timestamp_key, expire_seconds)
        except:
            return full_url

    escaped_domain = re.escape(domain)
    # 匹配 URL，并在结尾处小心处理 markdown 括号
    pattern = rf"https?://{escaped_domain}[^\s\"')\]]*"
    
    return re.sub(pattern, replacer, content)
