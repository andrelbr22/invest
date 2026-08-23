from pathlib import Path

from investment_engine.infrastructure.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_keeps_database_and_api_private():
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    assert '"5432:5432"' not in compose
    assert '"8000:8000"' not in compose
    assert "internal: true" in compose
    assert "INVESTMENT_API_URL: http://api:8000" in compose
    assert "POSTGRES_PASSWORD:?" in compose


def test_private_files_are_excluded_from_git_and_docker_build():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env.production" in gitignore
    assert "deployment/secrets/streamlit_secrets.toml" in gitignore
    assert ".env.production" in dockerignore
    assert "deployment/secrets/streamlit_secrets.toml" in dockerignore


def test_landing_page_and_private_beta_configuration_are_present():
    page = (ROOT / "deployment" / "site" / "index.html").read_text(encoding="utf-8")
    ui = (ROOT / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    assert "Formação do Investidor" in page
    assert "https://app.formacaodoinvestidor.com.br" in page
    assert 'os.getenv("INVESTMENT_API_URL"' in ui
    assert "CURRENT_USER_EMAIL" in ui
    assert 'api_get("/access/me")' in ui
    assert "st.login()" in ui and "st.logout()" in ui


def test_allowed_hosts_are_parsed_from_environment_shape():
    settings = Settings(allowed_hosts="api, localhost,127.0.0.1")
    assert settings.allowed_hosts_list == ["api", "localhost", "127.0.0.1"]


def test_owner_email_uses_new_setting_and_legacy_fallback():
    assert Settings(app_owner_emails="Owner@Example.com").owner_emails == {"owner@example.com"}
    assert Settings(app_allowed_emails="legacy@example.com").owner_emails == {"legacy@example.com"}
