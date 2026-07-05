from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application runtime settings.

    Attributes:
        app_name: Public application name.
        app_version: Semantic version for the API.
        environment: Runtime environment marker, e.g. local or production.
        debug: Enables debug mode when set to True.
        api_v1_prefix: Prefix for version 1 API routes.
    """

    app_name: str = "FastAPI Starter"
    app_version: str = "0.1.0"
    environment: str = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    secret_key: str
    jwt_algorithm: str
    database_url: str 
    jwt_expiration_minutes: int 
    max_requests: int
    window_seconds: int

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance.

    Returns:
        Settings: The singleton settings object.
    """

    return Settings()
