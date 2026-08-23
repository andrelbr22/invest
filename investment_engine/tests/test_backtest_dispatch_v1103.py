from pathlib import Path

import pytest

from investment_engine.integrations.github_actions import (
    GitHubActionsError,
    dispatch_official_backtests,
    list_workflow_runs,
)
from scripts.run_weekly_backtests import normalize_database_url, resolve_database_url


ROOT = Path(__file__).resolve().parents[1]


class Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class Http:
    def __init__(self, *, post_status=204, get_status=200, payload=None):
        self.post_status = post_status
        self.get_status = get_status
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response(self.post_status)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Response(self.get_status, self.payload)


def test_database_url_resolver_rejects_neon_console_and_uses_valid_fallback():
    resolved = resolve_database_url({
        "DATABASE_ADMIN_URL": "https://console.neon.tech/app/projects/example",
        "DATABASE_URL": "postgresql://owner:password@example.neon.tech/neondb?sslmode=require",
    })
    assert resolved.startswith("postgresql+psycopg://")
    assert normalize_database_url('DATABASE_URL = "postgres://user:pass@host/db"') == (
        "postgresql+psycopg://user:pass@host/db"
    )


def test_database_url_resolver_gives_safe_instruction_for_invalid_secret():
    with pytest.raises(SystemExit, match="Não use o endereço https:// do painel Neon"):
        resolve_database_url({"DATABASE_ADMIN_URL": "https://console.neon.tech"})


def test_dispatch_correlates_registered_job_with_workflow():
    http = Http()
    result = dispatch_official_backtests(
        token="secret", tickers=["BBAS3"], job_id="job-123", http=http,
    )
    assert result["job_id"] == "job-123"
    assert http.calls[0][2]["json"]["inputs"]["job_id"] == "job-123"


def test_recent_workflow_runs_are_reduced_to_safe_status_fields():
    http = Http(payload={"workflow_runs": [{
        "id": 99, "run_number": 4, "display_title": "Backtests oficiais • job-123",
        "status": "completed", "conclusion": "failure", "created_at": "2026-08-23T20:27:00Z",
        "updated_at": "2026-08-23T20:28:00Z", "html_url": "https://github.example/run/99",
        "head_commit": {"message": "campo que não deve sair"},
    }]})
    rows = list_workflow_runs(token="secret", http=http)
    assert rows == [{
        "id": 99, "run_number": 4, "display_title": "Backtests oficiais • job-123",
        "status": "completed", "conclusion": "failure", "created_at": "2026-08-23T20:27:00Z",
        "updated_at": "2026-08-23T20:28:00Z", "html_url": "https://github.example/run/99",
    }]


def test_v1103_registers_jobs_before_dispatch_and_has_failure_endpoint():
    api_source = (ROOT / "investment_engine" / "api" / "app.py").read_text(encoding="utf-8")
    ui_source = (ROOT / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "backtests-semanais.yml").read_text(encoding="utf-8")
    assert '@app.post("/backtests/batch/jobs")' in api_source
    assert '@app.patch("/backtests/batch/jobs/{job_id}/failed")' in api_source
    assert ui_source.index('api_post("/backtests/batch/jobs"') < ui_source.index("dispatch_official_backtests(", ui_source.index("def _render_official_backtest_admin"))
    assert "--validate-database-only" in workflow
    assert "MANUAL_JOB_ID" in workflow


def test_workflow_status_failure_is_presented_without_secret_contents():
    with pytest.raises(GitHubActionsError, match="consultar"):
        list_workflow_runs(token="secret", http=Http(get_status=403))
