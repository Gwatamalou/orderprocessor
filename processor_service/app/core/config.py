from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    rabbitmq_url: str
    service_name: str = "processor_service"
    log_level: str = "INFO"
    cors_origins: str = "*"
    rabbitmq_prefetch_count: int = 10
    db_pool_size: int = 20
    db_max_overflow: int = 10

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("Only PostgreSQL is supported")
        return v


settings = Settings()
