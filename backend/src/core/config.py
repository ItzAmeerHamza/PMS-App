from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "PharmaCare API"
    app_version: str = "0.1.0"
    debug: bool = True
    database_url: str = "sqlite:///./data/pharmacy.db"
    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
