from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, validator


class Settings(BaseSettings):
    PROJECT_NAME: str = "Hualpen Transport Optimization System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str
    DATABASE_SYNC_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # Google OR-Tools
    ORTOOLS_MAX_TIME_SECONDS: int = 300
    ORTOOLS_NUM_SEARCH_WORKERS: int = 4
    
    # Environment
    ENVIRONMENT: str = "development"
    
    # Additional settings (ignore extras for now)
    POSTGIS_VERSION: str = "3.4"
    LOG_LEVEL: str = "info"
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()