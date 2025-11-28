from typing import Literal

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # App
    # 应用基础配置
    APP_NAME: str = Field(default='FastAPI AI Backend', description='应用名称')
    APP_VERSION: str = Field(default='1.0.0', description='应用版本')
    ENVIRONMENT: Literal['development', 'staging', 'production'] = Field(default='development', description='运行环境')
    DEBUG: bool = Field(default=False, description='调试模式')

    # 服务器配置
    HOST: str = Field(default='0.0.0.0', description='服务器主机')
    PORT: int = Field(default=8000, description='服务器端口')
    # Pydantic配置

    # 数据库配置
    DATABASE_URL: str = Field(description='数据库连接URL')
    DATABASE_POOL_SIZE: int = Field(default=20, description='数据库连接池大小')
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description='数据库最大溢出连接')
    # JWT
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", description='JWT密钥')
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    # url前缀设置 API_V1_PREFIX: str = "/api/v1"
    API_V1_PREFIX: str = Field("/api/v1", description="API 路径前缀")
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=True, extra='ignore')

    @property
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self.ENVIRONMENT == 'development'

    @property
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.ENVIRONMENT == 'production'

    @property
    def database_url_sync(self) -> str:
        """同步数据库URL (用于Alembic)"""
        return str(self.DATABASE_URL).replace('+asyncpg', '')


# 根据环境加载不同配置文件
def get_settings() -> Settings:
    import os
    import pathlib

    # 项目根目录（假设 settings.py 在 app/core/）
    BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent  # 项目根 AI

    env = os.getenv('ENVIRONMENT', 'development')
    # print(f'[DEBUG] 系统环境变量 ENVIRONMENT = {env}')

    # 使用绝对路径
    env_file_map = {
        'development': BASE_DIR / '.env.dev',
        'staging': BASE_DIR / '.env.staging',
        'production': BASE_DIR / '.env.prod',
    }
    env_file = env_file_map.get(env, BASE_DIR / '.env')
    # print(f'[DEBUG] 即将加载配置文件: {env_file}')

    # 强制打印文件是否存在
    print(f'[DEBUG] 文件是否存在？: {env_file.exists()} -> {env_file.resolve()}')

    return Settings(_env_file=env_file)


# 全局配置实例
settings = get_settings()
