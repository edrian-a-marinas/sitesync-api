from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    DEBUG: bool = False
    SECRET_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"
    GROQ_API_KEY: str

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
