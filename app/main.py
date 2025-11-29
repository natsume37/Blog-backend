from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time
from app.core.database import SessionLocal
from app.models.monitor import VisitLog

from app.core.config import settings
from app.core.database import engine, Base
from app.routers import auth, articles, categories, messages, site, users, monitor, comments, changelog


# Create database tables
Base.metadata.create_all(bind=engine)


def get_location_from_ip(ip: str):
    """
    Simple IP to location resolver.
    In production, use a library like ip2region or GeoLite2.
    """
    if ip in ["127.0.0.1", "localhost", "::1"] or ip.startswith("192.168.") or ip.startswith("10."):
        return "北京", "北京"
    return "", ""


app = FastAPI(
    title=settings.APP_NAME,
    description="博客后端 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Visit Logger Middleware
@app.middleware("http")
async def log_visit(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Only log API requests, exclude OPTIONS and static files if any
    if request.url.path.startswith(settings.API_V1_PREFIX) and request.method != "OPTIONS":
        # Exclude admin/monitor APIs to avoid noise
        if "/monitor/" not in request.url.path and "/admin/" not in request.url.path:
            try:
                db = SessionLocal()
                # Simple IP resolution (Mock for now, or use a library if available)
                ip = request.client.host if request.client else "unknown"
                
                # Resolve location
                province, city = get_location_from_ip(ip)
                
                log = VisitLog(
                    ip=ip,
                    location=f"{province} {city}".strip(),
                    province=province,
                    city=city,
                    path=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    user_agent=request.headers.get("user-agent", ""),
                    process_time=process_time
                )
                db.add(log)
                db.commit()
                db.close()
            except Exception as e:
                print(f"Failed to log visit: {e}")
                
    return response


# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(articles.router, prefix=settings.API_V1_PREFIX)
app.include_router(categories.router, prefix=settings.API_V1_PREFIX)
app.include_router(messages.router, prefix=settings.API_V1_PREFIX)
app.include_router(site.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(monitor.router, prefix=settings.API_V1_PREFIX)
app.include_router(comments.router, prefix=settings.API_V1_PREFIX)
app.include_router(changelog.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {"message": "Welcome to Blog API", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
