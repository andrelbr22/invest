from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _service_block(compose: str, service: str, next_service: str) -> str:
    start = compose.index(f"  {service}:\n")
    return compose[start:compose.index(f"  {next_service}:\n", start + 1)]


def _read_generated_env(path: Path) -> dict[str, str]:
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        result[key] = value
    return result


def test_staging_uses_its_own_cookie_runtime_and_never_mounts_production_secrets():
    compose = _read("docker-compose.oracle-web.yml")
    production = _service_block(compose, "app", "staging")
    staging = _service_block(compose, "staging", "worker")
    application = _read("investment_engine/api/app.py")
    config = _read("investment_engine/infrastructure/config.py")

    assert "./deployment/runtime/staging.env" in staging
    assert "SESSION_COOKIE_NAME: fdi_production_session" in production
    assert "app_secrets.toml:/app/secrets/app_secrets.toml" not in staging
    assert "session_cookie=settings.session_cookie_name" in application
    assert 'session_cookie_name: str = "fdi_session"' in config
    assert "deployment/runtime/*.env" in _read(".gitignore")
    assert "deployment/runtime/*.env" in _read(".dockerignore")


def test_staging_runtime_generator_preserves_private_keys_and_excludes_production_tokens(tmp_path):
    output = tmp_path / "staging.env"
    generator = ROOT / "deployment" / "create-staging-runtime.py"
    source = ROOT / "deployment" / "secrets" / "app_secrets.toml.example"
    command = [
        sys.executable,
        str(generator),
        "--source", str(source),
        "--output", str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    first = _read_generated_env(output)
    first_url = urlsplit(first["DATABASE_URL"])
    assert unquote(first_url.username or "") == "investment_staging"
    assert first_url.path == "/investment_engine_staging"
    assert len(first["SESSION_SECRET"]) >= 32
    assert first["SESSION_COOKIE_NAME"] == "fdi_staging_session"
    assert first["OAUTH_REDIRECT_URI"].endswith("/testefdi/oauth2callback")
    assert "DATABASE_ADMIN_URL" not in first
    assert "BACKTEST_CALLBACK_TOKEN" not in first
    assert "GITHUB_ACTIONS_TOKEN" not in first

    password = unquote(first_url.password or "")
    session_secret = first["SESSION_SECRET"]
    subprocess.run(command, check=True, capture_output=True, text=True)
    second = _read_generated_env(output)
    assert unquote(urlsplit(second["DATABASE_URL"]).password or "") == password
    assert second["SESSION_SECRET"] == session_secret
    if os.name != "nt":
        assert output.stat().st_mode & 0o077 == 0


def test_staging_clone_scrubs_active_credentials_and_uses_a_restricted_database_role():
    refresh = _read("deployment/refresh-staging-db.sh")
    update = _read("deployment/update-staging-from-github.sh")

    assert "TRUNCATE TABLE public.email_login_codes" in refresh
    assert "WHERE status IN ('queued', 'running')" in refresh
    assert "staging_clone_quiesced" in refresh
    assert "investment_staging" in refresh
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION" in refresh
    assert 'psql -v ON_ERROR_STOP=1 -U "${STAGING_USER}" -d "${STAGING_DB}"' in refresh
    assert "REASSIGN OWNED BY investment TO investment_staging" not in refresh
    assert "create-staging-runtime.py" in update
    assert update.index("create-staging-runtime.py") < update.index("build staging")


def test_authentication_error_is_provider_neutral():
    application = _read("investment_engine/api/app.py")
    assert "authenticated_account_required" in application
    assert "authenticated_google_account_required" not in application


def test_publication_blocks_real_secret_toml_files_but_keeps_examples():
    publication = _read("PUBLICAR_GITHUB.ps1")
    dockerignore = _read(".dockerignore")
    worker_example = _read("deployment/second-instance/worker_secrets.toml.example")
    assert '$looksLikeSecretConfig' in publication
    assert '$lowerName -like "*secret*"' in publication
    assert '$lowerName.EndsWith(".example")' in publication
    assert "deployment/secrets/**" in dockerignore
    assert "!deployment/secrets/*.example" in dockerignore
    assert ".env*" in dockerignore
    assert "!.env.example" in dockerignore
    assert "*.save" in dockerignore
    assert "*.backup" in dockerignore
    assert 'APP_OWNER_EMAILS = "seu-email@gmail.com"' in worker_example
