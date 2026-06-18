from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # .env / secrets
    DATABASE_URL: str
    TEST_DATABASE_URL: str

    DEBUG: bool = False
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_URL: str = "redis://localhost:6379/1"

    GROQ_API_KEY: str

    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"

    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None

    # Constants / hard coded
    PROJECTS_TTL: int = 120

    OWNER_DASHBOARD_TTL: int = 60
    MANAGER_DASHBOARD_TTL: int = 60

    ROW_LIMIT: int = 20

    # Sync URL for Alembic migrations (asyncpg not supported by Alembic)
    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")

    # Controls debug mode and hides docs in production
    @property
    def app_config(self) -> dict:
        return {
            "debug": self.DEBUG,
            "docs_url": "/docs" if self.DEBUG else None,
            "redoc_url": "/redoc" if self.DEBUG else None,
            "openapi_url": "/openapi.json" if self.DEBUG else None,
        }

    class Config:
        env_file = ".env"


settings = Settings()
