from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://investment:investment@localhost:5432/investment"
    database_echo: bool = False
    app_environment: str = "development"
    api_docs_enabled: bool = True
    allowed_hosts: str = "localhost,127.0.0.1,testserver,api"
    default_currency: str = "BRL"
    data_stale_hours_market: int = 6
    data_stale_hours_fundamentals: int = 72
    gordon_required_return_pct: float = 12.0
    gordon_growth_pct: float = 4.0
    valuation_margin_of_safety_pct: float = 20.0
    app_auth_required: bool = False
    app_owner_emails: str = ""
    # Backward compatibility: the former allow-list becomes the initial owner
    # list when APP_OWNER_EMAILS has not been configured yet.
    app_allowed_emails: str = ""
    backtest_callback_token: str = ""
    alert_monitor_enabled: bool = False
    alert_monitor_poll_seconds: int = 60
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Formação do Investidor"
    smtp_starttls: bool = True

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    @property
    def owner_emails(self) -> set[str]:
        raw = self.app_owner_emails or self.app_allowed_emails
        return {item.strip().lower() for item in raw.split(",") if item.strip()}

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from_email.strip())


settings = Settings()
