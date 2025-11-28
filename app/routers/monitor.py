"""
服务器监控 API - 跨平台兼容 (Windows/Linux/Mac)
"""
import platform
import time
import os
from datetime import datetime
from typing import List, Optional

import psutil
from fastapi import APIRouter, Depends

from app.core.deps import get_current_admin
from app.models.user import User
from app.schemas.common import ResponseModel


router = APIRouter(prefix="/monitor", tags=["监控"])

# 服务启动时间
SERVER_START_TIME = time.time()


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
