from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LinkPlease"
    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/linkplease")
    pseudogram_api_key: str = ""
    pseudogram_base_url: str = "https://pseudogram-api.onrender.com/"
    max_retry_attempts: int = 5
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
