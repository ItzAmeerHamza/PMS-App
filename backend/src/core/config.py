from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PharmaCare API"
    app_version: str = "0.1.0"
    debug: bool = True
    # Not used: the SQLite location comes from src/core/paths.py. Kept so an old .env still loads.
    database_url: str = ""
    cors_origins: str = "*"
    # Acknowledged sync_outbox rows older than this may be purged (core/outbox.purge_synced).
    outbox_retention_days: int = 30
    # Cloud sync (phase 07 Part B). Empty URL means the worker has nowhere to send
    # events; the shop still runs. Read again from the environment on each cycle
    # (PHARMACARE_CLOUD_API_URL, else CLOUD_API_URL) so a restart picks up a change.
    # PHARMACARE_SYNC_AUTOSTART=0 keeps the background thread off (tests).
    # PHARMACARE_SYNC_INTERVAL_SECONDS (default 300), PHARMACARE_SYNC_BATCH_SIZE (100),
    # PHARMACARE_SYNC_TIMEOUT_SECONDS (30).

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
