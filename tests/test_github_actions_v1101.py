from pathlib import Path

import pytest
import requests

from investment_engine.integrations.github_actions import (
    GitHubActionsError,
    cancel_workflow_run,
    dispatch_official_backtests,
    normalize_tickers,
)


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class Http:
    def __init__(self, status_code=204, error=None):
        self.status_code = status_code
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return Response(self.status_code)


def test_normalize_tickers_removes_duplicates_and_validates_limit():
    assert normalize_tickers([" petr4 ", "PETR4", "vale3"]) == ["PETR4", "VALE3"]
    with pytest.raises(ValueError, match="pelo menos um"):
        normalize_tickers([])
    with pytest.raises(ValueError, match="no máximo 100"):
        normalize_tickers([f"TEST{i}" for i in range(101)])


def test_dispatch_sends_expected_private_github_request():
    http = Http()
    result = dispatch_official_backtests(
        token="secret-token", tickers=["petr4", "vale3"], http=http
    )
    assert result["submitted"] is True
    assert result["tickers"] == ["PETR4", "VALE3"]
    url, request = http.calls[0]
    assert url.endswith("/andrelbr22/invest/actions/workflows/backtests-semanais.yml/dispatches")
    assert request["headers"]["Authorization"] == "Bearer secret-token"
    assert request["json"] == {
        "ref": "main",
        "inputs": {"tickers": "PETR4,VALE3", "max_combinations": "200"},
    }


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "inválida"), (403, "permissão"), (404, "não foi encontrado"), (422, "recusou")],
)
def test_dispatch_translates_github_failures(status, message):
    with pytest.raises(GitHubActionsError, match=message):
        dispatch_official_backtests(token="token", tickers=["BBAS3"], http=Http(status))


def test_dispatch_handles_network_failure_without_leaking_token():
    with pytest.raises(GitHubActionsError, match="não respondeu") as error:
        dispatch_official_backtests(
            token="do-not-leak", tickers=["BBAS3"],
            http=Http(error=requests.ConnectionError("offline")),
        )
    assert "do-not-leak" not in str(error.value)


def test_cancel_targets_only_the_selected_workflow_run():
    http = Http(status_code=202)
    result = cancel_workflow_run(token="secret-token", run_id=12345, http=http)
    assert result == {"cancel_requested": True, "already_finished": False, "run_id": 12345}
    url, request = http.calls[0]
    assert url.endswith("/andrelbr22/invest/actions/runs/12345/cancel")
    assert request["headers"]["Authorization"] == "Bearer secret-token"


def test_cancel_reports_a_run_that_already_finished_without_leaking_token():
    secret = "do-not-leak"
    result = cancel_workflow_run(token=secret, run_id=12345, http=Http(status_code=409))
    assert result["already_finished"] is True
    assert secret not in str(result)


def test_workflow_runs_batch_as_a_module():
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "backtests-semanais.yml"
    contents = workflow.read_text(encoding="utf-8")
    assert contents.count("python -m scripts.run_weekly_backtests") == 2
    assert "python scripts/run_weekly_backtests.py" not in contents
