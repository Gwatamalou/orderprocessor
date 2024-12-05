from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    rabbitmq_url: str
    service_name: str = "processor-service"
    log_level: str = "INFO"


settings = Settings()
