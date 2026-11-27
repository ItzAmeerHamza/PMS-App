"""Cloud API settings, read from the environment (Railway variables in production)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Railway gives postgres:// or postgresql://; SQLAlchemy needs the psycopg 3 driver name."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "PharmaCare Cloud API"
    database_url: str = "postgresql+psycopg://localhost/pharmacare_cloud_dev"
    owner_session_hours: int = 12
    max_events_per_push: int = 500
    cors_origins: str = ""  # the dashboard origin(s), comma-separated; empty = no CORS
    # True in production (HTTPS). Local tests and http://127.0.0.1 stay false so the cookie is stored.
    cookie_secure: bool = False

    @property
    def sqlalchemy_url(self) -> str:
        return normalize_database_url(self.database_url)

    def __repr__(self) -> str:  # never print the database password
        return f"Settings(app_name={self.app_name!r}, database=<hidden>)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
