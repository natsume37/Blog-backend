from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
import ipaddress
import json
from functools import lru_cache
from urllib.request import urlopen
from urllib.request import Request as UrlRequest
from urllib.error import URLError, HTTPError
from contextlib import asynccontextmanager
from starlette.background import BackgroundTask, BackgroundTasks
from app.core.database import SessionLocal
from app.models.monitor import VisitLog

from app.core.config import settings
from app.core.logger import setup_logging
from app.routers import (
    ai,
    articles,
    audit_logs,
    auth,
    categories,
    changelog,
    friend_links,
    login_logs,
    monitor,
    plugins,
    records,
    resources,
    site,
    tool_items,
    upload,
    users,
    wechat,
)
from app.routers.v2 import records as records_v2
from app.tasks import start_scheduler, stop_scheduler

# Setup logging
setup_logging()
logger = logging.getLogger("app")


def _is_private_or_loopback_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return bool(ip_obj.is_private or ip_obj.is_loopback)
    except ValueError:
        return ip in ["127.0.0.1", "localhost", "::1"] or ip.startswith(("192.168.", "10."))


@lru_cache(maxsize=4096)
def _resolve_public_ip_location(ip: str) -> tuple[str, str]:
    """Resolve public IP location via configurable GeoIP provider."""
    if not settings.GEOIP_ENABLED:
        return "", ""

    url = settings.GEOIP_PROVIDER_URL.replace("{ip}", ip)
    timeout = 1.5
    req = UrlRequest(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (BlogBackend/1.0; +https://martin88.xyz)",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

    # Support common response formats. Primary target: ip2location / ipwho.is
    if isinstance(payload, dict):
        success = payload.get("success")
        if success is False:
            return "", ""

        province = str(
            payload.get("region")
            or payload.get("province")
            or payload.get("region_name")
            or ""
        ).strip()
        city = str(payload.get("city") or payload.get("city_name") or "").strip()
        return province, city

    return "", ""

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup")
    # Start scheduler
    start_scheduler()
    yield
    # Stop scheduler
    stop_scheduler()
    logger.info("Application shutdown")

def get_location_from_ip(ip: str):
    """
    Resolve IP location.
    - Private/loopback: 内网 局域网
    - Public IP: configurable GeoIP provider (optional)
    """
    if _is_private_or_loopback_ip(ip):
        return "内网", "局域网"

    try:
        province, city = _resolve_public_ip_location(ip)
        if province or city:
            return province, city
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, ValueError, OSError) as e:
        logger.debug(f"GeoIP resolve failed for {ip}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected GeoIP resolve error for {ip}: {e}")

    return "", ""


def get_client_ip(request: Request) -> str:
    """Resolve client IP behind reverse proxy."""
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
    return request.client.host if request.client else "unknown"


def write_visit_log(payload: dict):
    """Write visit log in background to avoid blocking API latency."""
    db = SessionLocal()
    try:
        log = VisitLog(**payload)
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log visit: {e}", exc_info=True)
    finally:
        db.close()


def append_background_task(response, task: BackgroundTask):
    """Preserve existing response background tasks while adding a new one."""
    if response.background is None:
        response.background = task
        return

    tasks = BackgroundTasks()
    tasks.add_task(response.background)
    tasks.add_task(task.func, *task.args, **task.kwargs)
    response.background = tasks


app = FastAPI(
    title=settings.APP_NAME,
    description="博客后端 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS, 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Referer Guard Middleware (Anti-leeching for API)
@app.middleware("http")
async def referer_guard(request: Request, call_next):
    # Skip if disabled or allowed all
    if not settings.ENABLE_REFERER_CHECK or "*" in settings.CORS_ORIGINS:
        return await call_next(request)
        
    # 两个 API 版本使用相同的来源校验策略。
    if request.url.path.startswith((settings.API_V1_PREFIX, settings.API_V2_PREFIX)):
        referer = request.headers.get("referer")
        if referer:
            # Check if referer matches any allowed origin
            allowed = False
            for origin in settings.CORS_ORIGINS:
                # Remove protocol for cleaner comparison if needed, or strict match
                if referer.startswith(origin):
                    allowed = True
                    break
            
            if not allowed:
                return JSONResponse(status_code=403, content={"code": 403, "msg": "Access denied (Invalid Referer)"})
                
    return await call_next(request)

# Visit Logger Middleware
@app.middleware("http")
async def log_visit(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Only log API requests, exclude OPTIONS and static files if any
    if request.url.path.startswith((settings.API_V1_PREFIX, settings.API_V2_PREFIX)) and request.method != "OPTIONS":
        # Exclude admin/monitor APIs to avoid noise
        if "/monitor/" not in request.url.path and "/admin/" not in request.url.path:
            ip = get_client_ip(request)
            province, city = get_location_from_ip(ip)
            payload = {
                "ip": ip,
                "location": f"{province} {city}".strip(),
                "province": province,
                "city": city,
                "path": request.url.path[:255],
                "method": request.method,
                "status_code": response.status_code,
                "user_agent": request.headers.get("user-agent", "")[:500],
                "process_time": process_time,
            }
            append_background_task(response, BackgroundTask(write_visit_log, payload))
                
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"},
    )


# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(articles.router, prefix=settings.API_V1_PREFIX)
app.include_router(categories.router, prefix=settings.API_V1_PREFIX)
app.include_router(site.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(monitor.router, prefix=settings.API_V1_PREFIX)
app.include_router(changelog.router, prefix=settings.API_V1_PREFIX)
app.include_router(upload.router, prefix="/api/v1")
app.include_router(resources.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(audit_logs.router, prefix="/api/v1")
app.include_router(login_logs.router, prefix="/api/v1")
app.include_router(friend_links.router, prefix="/api/v1")
app.include_router(tool_items.router, prefix="/api/v1")
app.include_router(plugins.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(records_v2.router, prefix=settings.API_V2_PREFIX)
app.include_router(wechat.router)


@app.get("/")
def root():
    return {"message": "Welcome to Blog API", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
