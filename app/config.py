from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://gridbricks:gridbricks@localhost:5432/gridbricks"
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    sync_interval_seconds: int = 120
    stale_after_seconds: int = 300
    refresh_cooldown_seconds: int = 60
    job_lease_seconds: int = 300
    bootstrap_history_days: int = 30
    bootstrap_demo: bool = False
    request_driven_sync: bool = False
    request_job_budget_seconds: int = 60
    http_timeout_seconds: float = 30
    frontend_dist: str = "frontend/dist"
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url


@lru_cache
def settings() -> Settings:
    return Settings()
