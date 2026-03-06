"""
服务器监控 API - 跨平台兼容 (Windows/Linux/Mac)
"""
import platform
import time
import os
from datetime import datetime, timedelta
from typing import List, Optional

import psutil
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User
from app.models.monitor import VisitLog
from app.schemas.common import ResponseModel, PagedData


router = APIRouter(prefix="/monitor", tags=["监控"])

# 服务启动时间
SERVER_START_TIME = time.time()

_EN_REGION_TO_CN = {
    "beijing": "北京市",
    "tianjin": "天津市",
    "shanghai": "上海市",
    "chongqing": "重庆市",
    "hebei": "河北省",
    "shanxi": "山西省",
    "liaoning": "辽宁省",
    "jilin": "吉林省",
    "heilongjiang": "黑龙江省",
    "jiangsu": "江苏省",
    "zhejiang": "浙江省",
    "anhui": "安徽省",
    "fujian": "福建省",
    "jiangxi": "江西省",
    "shandong": "山东省",
    "henan": "河南省",
    "hubei": "湖北省",
    "hunan": "湖南省",
    "guangdong": "广东省",
    "hainan": "海南省",
    "sichuan": "四川省",
    "guizhou": "贵州省",
    "yunnan": "云南省",
    "shaanxi": "陕西省",
    "shanxi sheng": "陕西省",
    "gansu": "甘肃省",
    "qinghai": "青海省",
    "taiwan": "台湾省",
    "inner mongolia": "内蒙古自治区",
    "guangxi": "广西壮族自治区",
    "tibet": "西藏自治区",
    "ningxia": "宁夏回族自治区",
    "xinjiang": "新疆维吾尔自治区",
    "hong kong": "香港特别行政区",
    "macao": "澳门特别行政区",
    "macau": "澳门特别行政区",
    # 城市兜底，解决“Wuhan 有数据但湖北为 0”
    "wuhan": "湖北省",
}


def _to_map_province_name(province: str, city: str) -> str:
    raw = (province or "").strip()
    if not raw:
        raw = (city or "").strip()
    if not raw:
        return ""

    lowered = raw.lower().replace("_", " ").replace("-", " ").replace(" province", "").strip()
    lowered = " ".join(lowered.split())
    if lowered in _EN_REGION_TO_CN:
        return _EN_REGION_TO_CN[lowered]

    if raw.endswith(("省", "市", "自治区", "特别行政区")):
        return raw

    # 中文无后缀时补齐，确保与 china.json 名称一致
    direct = {
        "北京": "北京市",
        "天津": "天津市",
        "上海": "上海市",
        "重庆": "重庆市",
        "内蒙古": "内蒙古自治区",
        "广西": "广西壮族自治区",
        "西藏": "西藏自治区",
        "宁夏": "宁夏回族自治区",
        "新疆": "新疆维吾尔自治区",
        "香港": "香港特别行政区",
        "澳门": "澳门特别行政区",
    }
    if raw in direct:
        return direct[raw]
    return f"{raw}省"


@router.get("/visits", response_model=ResponseModel[PagedData])
def get_visit_logs(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取访问日志列表"""
    query = db.query(VisitLog).order_by(VisitLog.created_at.desc())
    
    total = query.count()
    logs = query.offset((current - 1) * size).limit(size).all()
    
    records = []
    for log in logs:
        records.append({
            "id": log.id,
            "ip": log.ip,
            "location": log.location,
            "province": log.province,
            "city": log.city,
            "path": log.path,
            "method": log.method,
            "status_code": log.status_code,
            "process_time": log.process_time,
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
        
    return ResponseModel(
        code=200,
        data=PagedData(
            records=records,
            total=total,
            current=current,
            size=size
        )
    )


@router.get("/map-stats", response_model=ResponseModel)
def get_map_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取地图统计数据（按省份分组）"""
    # Group by province + city, then fold to map province name
    stats = db.query(
        VisitLog.province,
        VisitLog.city,
        func.count(VisitLog.id).label('count')
    ).filter(
        (VisitLog.province != "") | (VisitLog.city != "")
    ).group_by(
        VisitLog.province,
        VisitLog.city
    ).all()

    merged: dict[str, int] = {}
    for province, city, count in stats:
        name = _to_map_province_name(province or "", city or "")
        if not name:
            continue
        merged[name] = merged.get(name, 0) + int(count or 0)

    result = [{"name": k, "value": v} for k, v in merged.items()]
    return ResponseModel(code=200, data=result)


@router.get("/dashboard", response_model=ResponseModel)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取后台仪表盘关键指标"""
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    seven_days_start = today_start - timedelta(days=6)

    today_visits = db.query(func.count(VisitLog.id)).filter(
        VisitLog.created_at >= today_start
    ).scalar() or 0

    draft_count = db.query(func.count(Article.id)).filter(
        Article.is_published == False
    ).scalar() or 0

    pending_comments = db.query(func.count(Comment.id)).filter(
        Comment.is_approved == False
    ).scalar() or 0

    hot_articles_raw = db.query(
        Article.id,
        Article.title,
        Article.view_count,
        Article.comment_count
    ).filter(
        Article.is_published == True
    ).order_by(
        Article.view_count.desc(),
        Article.comment_count.desc(),
        Article.id.desc()
    ).limit(5).all()

    hot_articles = [{
        "id": int(row.id),
        "title": row.title,
        "view_count": int(row.view_count or 0),
        "comment_count": int(row.comment_count or 0)
    } for row in hot_articles_raw]

    trend_raw = db.query(
        func.date(VisitLog.created_at).label("day"),
        func.count(VisitLog.id).label("count")
    ).filter(
        VisitLog.created_at >= seven_days_start
    ).group_by(
        func.date(VisitLog.created_at)
    ).all()

    trend_map = {str(row.day): int(row.count or 0) for row in trend_raw}
    visit_trend = []
    for i in range(7):
        day = seven_days_start + timedelta(days=i)
        key = day.strftime("%Y-%m-%d")
        visit_trend.append({
            "date": key,
            "count": trend_map.get(key, 0)
        })

    return ResponseModel(code=200, data={
        "today_visits": int(today_visits),
        "draft_count": int(draft_count),
        "pending_comments": int(pending_comments),
        "visit_trend_7d": visit_trend,
        "hot_articles": hot_articles
    })


def get_disk_path() -> str:
    """获取磁盘路径 - 跨平台兼容"""
    if platform.system() == "Windows":
        return "C:\\"
    return "/"


def safe_get_cpu_freq() -> dict:
    """安全获取 CPU 频率"""
    try:
        freq = psutil.cpu_freq()
        if freq:
            return {
                "freq_current": round(freq.current, 2),
                "freq_max": round(freq.max, 2) if freq.max else round(freq.current, 2)
            }
    except Exception:
        pass
    return {"freq_current": 0, "freq_max": 0}


def safe_get_disk_io() -> dict:
    """安全获取磁盘 IO"""
    try:
        disk_io = psutil.disk_io_counters()
        if disk_io:
            return {
                "read_bytes": disk_io.read_bytes,
                "write_bytes": disk_io.write_bytes
            }
    except Exception:
        pass
    return {"read_bytes": 0, "write_bytes": 0}


@router.get("/system", response_model=ResponseModel)
def get_system_info(current_user: User = Depends(get_current_admin)):
    """获取系统信息（管理员）- 跨平台兼容"""
    try:
        # CPU 信息
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=False) or 1
        cpu_count_logical = psutil.cpu_count(logical=True) or 1
        cpu_freq_info = safe_get_cpu_freq()
        
        # 内存信息
        memory = psutil.virtual_memory()
        try:
            swap = psutil.swap_memory()
            swap_info = {
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": swap.percent
            }
        except Exception:
            swap_info = {"swap_total": 0, "swap_used": 0, "swap_percent": 0}
        
        # 磁盘信息 - 跨平台
        disk_path = get_disk_path()
        try:
            disk = psutil.disk_usage(disk_path)
            disk_info = {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent
            }
        except Exception:
            disk_info = {"total": 0, "used": 0, "free": 0, "percent": 0}
        
        disk_io_info = safe_get_disk_io()
        disk_info.update(disk_io_info)
        
        # 网络信息
        try:
            net_io = psutil.net_io_counters()
            network_info = {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        except Exception:
            network_info = {"bytes_sent": 0, "bytes_recv": 0, "packets_sent": 0, "packets_recv": 0}
        
        # 系统时间信息
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = time.time() - psutil.boot_time()
        except Exception:
            boot_time = datetime.now()
            uptime = 0
        
        server_uptime = time.time() - SERVER_START_TIME
        
        # 处理器信息 - Windows 可能返回空字符串
        processor = platform.processor()
        if not processor:
            processor = platform.machine()
        
        return ResponseModel(
            code=200,
            data={
                "os": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version()[:50] if len(platform.version()) > 50 else platform.version(),
                    "machine": platform.machine(),
                    "processor": processor,
                    "hostname": platform.node(),
                    "python_version": platform.python_version()
                },
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "count_logical": cpu_count_logical,
                    **cpu_freq_info
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "used": memory.used,
                    "percent": memory.percent,
                    **swap_info
                },
                "disk": disk_info,
                "network": network_info,
                "time": {
                    "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "uptime": int(uptime),
                    "server_uptime": int(server_uptime),
                    "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
        )
    except Exception as e:
        return ResponseModel(code=500, msg=f"获取系统信息失败: {str(e)}")


@router.get("/realtime", response_model=ResponseModel)
def get_realtime_stats(current_user: User = Depends(get_current_admin)):
    """获取实时统计数据（管理员）- 用于定时刷新"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        disk_path = get_disk_path()
        try:
            disk = psutil.disk_usage(disk_path)
            disk_percent = disk.percent
        except Exception:
            disk_percent = 0
        
        try:
            net_io = psutil.net_io_counters()
            network_sent = net_io.bytes_sent
            network_recv = net_io.bytes_recv
        except Exception:
            network_sent = 0
            network_recv = 0
        
        return ResponseModel(
            code=200,
            data={
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "memory_available": memory.available,
                "disk_percent": disk_percent,
                "network_sent": network_sent,
                "network_recv": network_recv,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
        )
    except Exception as e:
        return ResponseModel(code=500, msg=f"获取实时数据失败: {str(e)}")


@router.get("/processes", response_model=ResponseModel)
def get_processes(
    limit: int = 10,
    sort_by: str = "memory",
    current_user: User = Depends(get_current_admin)
):
    """获取进程列表（管理员）- 跨平台兼容"""
    try:
        processes = []
        
        # 使用安全的方式迭代进程
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'create_time']):
            try:
                info = proc.info
                # 安全获取创建时间
                create_time_str = ""
                if info.get('create_time'):
                    try:
                        create_time_str = datetime.fromtimestamp(info['create_time']).strftime("%Y-%m-%d %H:%M:%S")
                    except (OSError, ValueError):
                        pass
                
                processes.append({
                    "pid": info.get('pid', 0),
                    "name": info.get('name', 'Unknown'),
                    "cpu_percent": round(info.get('cpu_percent') or 0, 2),
                    "memory_percent": round(info.get('memory_percent') or 0, 2),
                    "status": info.get('status', 'unknown'),
                    "create_time": create_time_str
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, PermissionError):
                continue
            except Exception:
                continue
        
        # 排序
        if sort_by == "cpu":
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        else:
            processes.sort(key=lambda x: x['memory_percent'], reverse=True)
        
        return ResponseModel(
            code=200,
            data={
                "processes": processes[:limit],
                "total": len(processes)
            }
        )
    except Exception as e:
        return ResponseModel(
            code=200,
            data={
                "processes": [],
                "total": 0,
                "error": f"获取进程列表时出错: {str(e)}"
            }
        )


@router.get("/connections", response_model=ResponseModel)
def get_connections(current_user: User = Depends(get_current_admin)):
    """获取网络连接信息（管理员）- 跨平台兼容
    
    注意：在 Windows 上需要管理员权限，在 Linux/Mac 上可能也需要 root 权限
    """
    connections = []
    error_msg = None
    
    try:
        # 在某些系统上 net_connections 需要特殊权限
        for conn in psutil.net_connections(kind='inet'):
            try:
                if conn.status in ('LISTEN', 'ESTABLISHED'):
                    local_addr = ""
                    remote_addr = ""
                    
                    if conn.laddr:
                        local_addr = f"{conn.laddr.ip}:{conn.laddr.port}"
                    if conn.raddr:
                        remote_addr = f"{conn.raddr.ip}:{conn.raddr.port}"
                    
                    connections.append({
                        "local_addr": local_addr,
                        "remote_addr": remote_addr,
                        "status": conn.status,
                        "pid": conn.pid or 0
                    })
            except Exception:
                continue
                
    except psutil.AccessDenied:
        error_msg = "权限不足，无法获取网络连接信息（需要管理员/root权限）"
    except PermissionError:
        error_msg = "权限被拒绝，无法访问网络连接信息"
    except Exception as e:
        error_msg = f"获取网络连接时出错: {str(e)}"
    
    result = {
        "connections": connections[:50],
        "total": len(connections)
    }
    
    if error_msg:
        result["warning"] = error_msg
    
    return ResponseModel(code=200, data=result)
