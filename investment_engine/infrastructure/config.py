from __future__ import annotations

import os
from pathlib import Path
import tomllib
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_application_secrets() -> None:
    """Load the self-hosted TOML file before Pydantic reads the environment."""
    configured = os.getenv("APP_SECRETS_FILE", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path("/app/secrets/app_secrets.toml"),
        Path("deployment/secrets/app_secrets.toml"),
    ]
    path = next((item for item in candidates if item is not None and item.is_file()), None)
    if path is None:
        return
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)):
            os.environ.setdefault(str(key).upper(), str(value))
    auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
    aliases = {
        "client_id": "GOOGLE_CLIENT_ID",
        "client_secret": "GOOGLE_CLIENT_SECRET",
        "cookie_secret": "SESSION_SECRET",
        "redirect_uri": "OAUTH_REDIRECT_URI",
        "server_metadata_url": "GOOGLE_SERVER_METADATA_URL",
    }
    for source, destination in aliases.items():
        value = auth.get(source)
        if value:
            os.environ.setdefault(destination, str(value))
    database_override = os.getenv("DATABASE_NAME_OVERRIDE", "").strip()
    if database_override and database_override.replace("_", "").isalnum():
        for variable in ("DATABASE_URL", "DATABASE_ADMIN_URL"):
            current = os.getenv(variable, "").strip()
            if not current:
                continue
            parsed = urlsplit(current)
            os.environ[variable] = urlunsplit((parsed.scheme, parsed.netloc, f"/{database_override}", parsed.query, parsed.fragment))


_load_application_secrets()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://investment:investment@localhost:5432/investment"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 2
    database_pool_timeout_seconds: int = 30
    database_pool_recycle_seconds: int = 1800
    database_statement_timeout_ms: int = 12000
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
    session_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_server_metadata_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    oauth_redirect_uri: str = ""
    canonical_url: str = "https://formacaodoinvestidor.com.br"
    secure_cookies: bool = True
    economy_headlines_ttl_seconds: int = 3600
    background_worker_poll_seconds: float = 2.0
    background_job_lease_timeout_seconds: int = 300
    log_level: str = "INFO"

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

    @property
    def google_auth_configured(self) -> bool:
        return bool(
            self.google_client_id.strip()
            and self.google_client_secret.strip()
            and len(self.session_secret.strip()) >= 32
        )


settings = Settings()
