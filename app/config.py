from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Game Production Control Hub"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/control_hub.db"
    claude_monthly_budget_usd: float = 10.0
    claude_soft_limit_usd: float = 8.0
    claude_stop_limit_usd: float = 9.0
    openai_monthly_budget_usd: float = 0.0
    external_ai_calls_enabled: bool = False
    gateway_default_policy: str = "record_only_no_external_calls"
    workspace_root: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def resolved_workspace_root(self) -> Path:
        return Path(self.workspace_root).resolve() if self.workspace_root else self.project_root


@lru_cache
def get_settings() -> Settings:
    return Settings()
