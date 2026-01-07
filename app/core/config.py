"""
应用配置模块 (Application Configuration Module)
包含基础配置、数据库配置、缓存配置、日志配置等。
"""
import os
from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ===========================
    # 基础配置 (Base)
    # ===========================
    APP_NAME: str = Field(default='FastAPI Blog Backend', description='应用名称')
    APP_VERSION: str = Field(default='1.0.0', description='应用版本')
    ENVIRONMENT: Literal['development', 'staging', 'production'] = Field(
        default='development', description='运行环境'
    )
    DEBUG: bool = Field(default=False, description='调试模式')

    # 项目根目录 (动态获取，指向 my_project/)
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    # ===========================
    # 日志配置 (Logging) - 新增
    # ===========================
    LOG_LEVEL: str = Field(default="INFO", description="日志等级: DEBUG/INFO/WARNING/ERROR")
    LOG_JSON_FORMAT: bool = Field(default=False, description="是否开启生产环境JSON日志格式")
    LOG_DIR: str = Field(default="logs", description="日志文件夹名称")
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 10  # 保留10个文件

    # ===========================
    # Redis 配置 (Redis)
    # ===========================
    REDIS_HOST: str = Field(default='localhost', description='Redis主机')
    REDIS_PORT: int = Field(default=6379, description='Redis端口')
    REDIS_DB: int = Field(default=0, description='Redis数据库索引')
    REDIS_PASSWORD: str | None = Field(default=None, description='Redis密码')
    REDIS_CACHE_TTL: int = Field(default=180, description='Redis缓存过期时间(秒)')

    # ===========================
    # 定时任务配置 (Scheduler)
    # ===========================
    SYNC_VIEWS_INTERVAL_MINUTES: int = Field(default=10, description='文章浏览量同步周期(分钟)')

    # ===========================
    # 服务器配置 (Server)
    # ===========================
    HOST: str = Field(default='0.0.0.0', description='服务器主机')
    PORT: int = Field(default=8000, description='服务器端口')
    API_V1_PREFIX: str = Field(default="/api/v1", description="API 路径前缀")

    # ===========================
    # 数据库配置 (Database)
    # ===========================
    DATABASE_URL: str = Field(default="sqlite:///./test.db", description='数据库连接URL')
    DATABASE_POOL_SIZE: int = Field(default=20, description='数据库连接池大小')
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description='数据库最大溢出连接')

    # ===========================
    # 安全配置 (Security)
    # ===========================
    SECRET_KEY: str = Field(default="insecure-key-change-me", description='JWT密钥')
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS & Referer
    CORS_ORIGINS: list[str] = Field(default=["*"], description="允许的跨域来源")
    ENABLE_REFERER_CHECK: bool = Field(default=False, description="是否开启严格Referer检查(防盗链)")

    # ===========================
    # 邮件配置 (Email)
    # ===========================
    SMTP_HOST: str = Field(default='smtp.example.com', description='SMTP服务器地址')
    SMTP_PORT: int = Field(default=465, description='SMTP服务器端口')
    SMTP_USER: str = Field(default='user@example.com', description='SMTP用户名')
    SMTP_PASSWORD: str = Field(default='password', description='SMTP密码')
    EMAILS_FROM_EMAIL: str = Field(default='user@example.com', description='发件人邮箱')
    EMAILS_FROM_NAME: str = Field(default='Martin-BLog', description='发件人名称')

    # ===========================
    # 七牛云文章配置 (Qiniu)
    # ===========================
    QINIU_ACCESS_KEY: str | None = Field(default=None, description="七牛云Access Key")
    QINIU_SECRET_KEY: str | None = Field(default=None, description="七牛云Secret Key")
    QINIU_BUCKET: str | None = Field(default=None, description="七牛云存储桶名称")
    QINIU_DOMAIN: str | None = Field(default=None, description="七牛云存储桶域名")

    # 七牛云时间戳防盗链配置
    QINIU_TIMESTAMP_ENABLED: bool = Field(default=False, description="是否启用七牛云时间戳防盗链")
    QINIU_TIMESTAMP_KEY: str | None = Field(default=None, description="七牛云时间戳防盗链密钥")
    QINIU_TIMESTAMP_EXPIRE: int = Field(default=3600, description="时间戳防盗链有效期(秒)")

    # ===========================
    # Pydantic 配置
    # ===========================
    # 允许从 .env 文件读取，同时忽略多余字段
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == 'development'

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == 'production'

    @property
    def database_url_sync(self) -> str:
        """同步数据库URL (用于Alembic)"""
        return str(self.DATABASE_URL).replace('+asyncpg', '')

    @property
    def is_qiniu_enabled(self) -> bool:
        """检查七牛云是否已配置且可用"""
        # Pydantic 会自动处理环境变量优先级: 系统环境变量 > .env文件
        return all([
            self.QINIU_ACCESS_KEY,
            self.QINIU_SECRET_KEY,
            self.QINIU_BUCKET,
            self.QINIU_DOMAIN
        ])

    @property
    def is_qiniu_timestamp_enabled(self) -> bool:
        """检查七牛云时间戳防盗链是否启用且已配置"""
        return self.QINIU_TIMESTAMP_ENABLED and bool(self.QINIU_TIMESTAMP_KEY)


# ===========================
# 加载逻辑
# ===========================
def get_settings() -> Settings:
    """
    根据 ENVIRONMENT 环境变量加载不同的配置文件
    优先级: 系统环境变量 > .env.prod/.dev > .env > 默认值
    """
    # 1. 先确定环境，默认 development
    env_mode = os.getenv('ENVIRONMENT', 'development')

    # 2. 确定根目录
    base_dir = Path(__file__).resolve().parent.parent.parent

    # 3. 映射环境文件
    env_files = {
        'development': '.env.dev',
        'staging': '.env.staging',
        'production': '.env.prod',
    }

    # 4. 确定目标文件路径
    target_env_file = base_dir / env_files.get(env_mode, '.env')

    # 5. 实例化 Settings，传入 _env_file 参数
    # 注意：如果文件不存在，Pydantic 会默认忽略或仅使用系统环境变量
    return Settings(_env_file=target_env_file)


# 全局单例
settings = get_settings()
