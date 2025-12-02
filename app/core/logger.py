# -*- coding: utf-8 -*-
"""
@File    : logger.py
@Author  : Martin
@Time    : 2025/12/2 10:52
@Desc    : 
"""
import sys
import json
import logging
import logging.config
from pathlib import Path
from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """
    自定义 JSON 格式化器，适用于生产环境日志收集 (ELK/EFK/Datadog)
    """

    def format(self, record: logging.LogRecord) -> str:
        # 基础字段
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
            "process_id": record.process,
            "thread_name": record.threadName,
        }

        # 异常堆栈信息
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # 处理 extra 参数: logger.info("msg", extra={"user_id": 123})
        # 过滤掉 LogRecord 原有的属性，只保留额外的
        skip_keys = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module",
            "msecs", "message", "msg", "name", "pathname", "process",
            "processName", "relativeCreated", "stack_info", "thread", "threadName"
        }

        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in skip_keys:
                    log_record[key] = value

        return json.dumps(log_record, ensure_ascii=False)


def setup_logging():
    """
    初始化日志配置
    """
    # 1. 准备日志目录
    log_path = settings.BASE_DIR / settings.LOG_DIR
    if not log_path.exists():
        log_path.mkdir(parents=True, exist_ok=True)

    # 2. 确定日志级别 (将字符串转为 logging 常量)
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # 3. 确定格式化器 (开发环境用 standard，生产环境可选 json)
    formatter_name = "json" if settings.LOG_JSON_FORMAT else "standard"

    # 4. 配置字典
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,  # 重要：防止 uvicorn 日志被禁用

        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": JSONFormatter,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },

        "handlers": {
            # 控制台输出
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": formatter_name,
                "stream": sys.stdout,
            },
            # Info 文件输出 (自动轮转)
            "file_info": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": formatter_name,
                "filename": log_path / "app.log",
                "maxBytes": settings.LOG_MAX_BYTES,
                "backupCount": settings.LOG_BACKUP_COUNT,
                "encoding": "utf-8",
            },
            # Error 文件输出 (单独记录错误)
            "file_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": formatter_name,
                "filename": log_path / "error.log",
                "maxBytes": settings.LOG_MAX_BYTES,
                "backupCount": settings.LOG_BACKUP_COUNT,
                "encoding": "utf-8",
            }
        },

        "loggers": {
            # 你的应用 Logger (名称建议设为 'app' 或项目名)
            "app": {
                "handlers": ["console", "file_info", "file_error"],
                "level": log_level,
                "propagate": False,
            },
            # 接管 Uvicorn 的日志，使其格式统一并输出到文件
            "uvicorn": {
                "handlers": ["console", "file_info"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console", "file_info"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console", "file_error"],
                "level": "INFO",
                "propagate": False,
            },
        }
    }

    logging.config.dictConfig(logging_config)