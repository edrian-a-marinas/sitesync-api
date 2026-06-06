from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")

    class Config:
        env_file = ".env"

settings = Settings()