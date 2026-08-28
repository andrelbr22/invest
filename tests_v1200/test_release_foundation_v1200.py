from pathlib import Path

from fastapi.testclient import TestClient

from investment_engine import __version__
from investment_engine.api.app import app


ROOT = Path(__file__).resolve().parents[1]


def test_version_and_health_are_v1200():
    assert __version__.startswith("1.20.")
    response = TestClient(app, base_url="http://localhost").get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == __version__
    assert response.headers.get("X-Request-ID")


def test_pytest_discovers_every_versioned_test_directory():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"tests_v1160"' in pyproject
    assert '"tests_v1170"' in pyproject
    assert '"tests_v1200"' in pyproject


def test_deployment_keeps_worker_opt_in():
    compose = (ROOT / "docker-compose.oracle-web.yml").read_text(encoding="utf-8")
    assert 'profiles: ["worker"]' in compose
    assert "start-worker.sh" in compose
