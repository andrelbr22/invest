from __future__ import annotations

from collections.abc import Iterable

import requests


DEFAULT_REPOSITORY = "andrelbr22/invest"
DEFAULT_WORKFLOW = "backtests-semanais.yml"
DEFAULT_REF = "main"
MAX_TICKERS = 100


class GitHubActionsError(RuntimeError):
    """Erro seguro e apresentável ao acionar um workflow do GitHub."""


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _clean_token(token: str) -> str:
    clean = str(token or "").strip()
    if not clean:
        raise GitHubActionsError("A integração com o GitHub ainda não foi configurada.")
    return clean


def _clean_repository(repository: str) -> str:
    clean = str(repository or "").strip().strip("/")
    if clean.count("/") != 1:
        raise GitHubActionsError("O repositório configurado para os backtests é inválido.")
    return clean


def normalize_tickers(tickers: Iterable[str]) -> list[str]:
    clean: list[str] = []
    for ticker in tickers:
        value = str(ticker or "").strip().upper()
        if value and value not in clean:
            clean.append(value)
    if not clean:
        raise ValueError("Selecione pelo menos um ativo.")
    if len(clean) > MAX_TICKERS:
        raise ValueError("Selecione no máximo 100 ativos.")
    return clean


def dispatch_official_backtests(
    *,
    token: str,
    tickers: Iterable[str],
    repository: str = DEFAULT_REPOSITORY,
    workflow: str = DEFAULT_WORKFLOW,
    ref: str = DEFAULT_REF,
    max_combinations: int = 200,
    job_id: str | None = None,
    http=requests,
) -> dict:
    """Solicita o lote oficial sem expor a credencial ao navegador."""

    clean_token = _clean_token(token)
    clean_repository = _clean_repository(repository)
    clean_workflow = str(workflow or "").strip()
    clean_ref = str(ref or "").strip()
    if not clean_workflow or not clean_ref:
        raise GitHubActionsError("Workflow ou branch do GitHub não foi configurado.")
    clean_tickers = normalize_tickers(tickers)
    combinations = max(1, min(int(max_combinations), 200))
    url = f"https://api.github.com/repos/{clean_repository}/actions/workflows/{clean_workflow}/dispatches"
    inputs = {
        "tickers": ",".join(clean_tickers),
        "max_combinations": str(combinations),
    }
    clean_job_id = str(job_id or "").strip()
    if clean_job_id:
        inputs["job_id"] = clean_job_id
    try:
        response = http.post(
            url,
            headers=_github_headers(clean_token),
            json={
                "ref": clean_ref,
                "inputs": inputs,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise GitHubActionsError("O GitHub não respondeu ao pedido de backtests.") from exc
    if response.status_code != 204:
        messages = {
            401: "A credencial do GitHub é inválida ou expirou.",
            403: "A credencial não possui permissão para executar o workflow.",
            404: "O repositório ou o workflow não foi encontrado pelo GitHub.",
            422: "O GitHub recusou os ativos ou a configuração enviada.",
        }
        raise GitHubActionsError(messages.get(response.status_code, f"O GitHub recusou o pedido (HTTP {response.status_code})."))
    return {
        "submitted": True,
        "tickers": clean_tickers,
        "max_combinations": combinations,
        "job_id": clean_job_id or None,
        "actions_url": f"https://github.com/{clean_repository}/actions/workflows/{clean_workflow}",
    }


def cancel_workflow_run(
    *,
    token: str,
    run_id: int,
    repository: str = DEFAULT_REPOSITORY,
    http=requests,
) -> dict:
    """Cancela uma execução específica sem revelar credenciais ou respostas internas."""

    clean_token = _clean_token(token)
    clean_repository = _clean_repository(repository)
    try:
        clean_run_id = int(run_id)
    except (TypeError, ValueError) as exc:
        raise GitHubActionsError("A execução do GitHub informada é inválida.") from exc
    if clean_run_id <= 0:
        raise GitHubActionsError("A execução do GitHub informada é inválida.")
    url = f"https://api.github.com/repos/{clean_repository}/actions/runs/{clean_run_id}/cancel"
    try:
        response = http.post(
            url,
            headers=_github_headers(clean_token),
            timeout=30,
        )
    except requests.RequestException as exc:
        raise GitHubActionsError("O GitHub não respondeu ao pedido de cancelamento.") from exc
    if response.status_code == 202:
        return {"cancel_requested": True, "already_finished": False, "run_id": clean_run_id}
    if response.status_code == 409:
        return {"cancel_requested": False, "already_finished": True, "run_id": clean_run_id}
    messages = {
        401: "A credencial do GitHub é inválida ou expirou.",
        403: "A credencial não possui permissão para cancelar o workflow.",
        404: "A execução do GitHub não foi encontrada.",
    }
    raise GitHubActionsError(
        messages.get(response.status_code, f"O GitHub recusou o cancelamento (HTTP {response.status_code}).")
    )


def list_workflow_runs(
    *,
    token: str,
    repository: str = DEFAULT_REPOSITORY,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = DEFAULT_REF,
    limit: int = 20,
    http=requests,
) -> list[dict]:
    """Consulta o andamento recente sem expor a credencial ao navegador."""

    clean_token = _clean_token(token)
    clean_repository = _clean_repository(repository)
    clean_workflow = str(workflow or "").strip()
    if not clean_workflow:
        raise GitHubActionsError("O workflow do GitHub não foi configurado.")
    url = f"https://api.github.com/repos/{clean_repository}/actions/workflows/{clean_workflow}/runs"
    try:
        response = http.get(
            url,
            headers=_github_headers(clean_token),
            params={
                "event": "workflow_dispatch",
                "branch": str(branch or DEFAULT_REF).strip(),
                "per_page": max(1, min(int(limit), 50)),
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise GitHubActionsError("O GitHub não respondeu à consulta de andamento.") from exc
    if response.status_code != 200:
        messages = {
            401: "A credencial do GitHub é inválida ou expirou.",
            403: "A credencial não possui permissão para consultar o workflow.",
            404: "O repositório ou o workflow não foi encontrado pelo GitHub.",
        }
        raise GitHubActionsError(messages.get(response.status_code, f"O GitHub recusou a consulta (HTTP {response.status_code})."))
    try:
        rows = response.json().get("workflow_runs") or []
    except (AttributeError, ValueError) as exc:
        raise GitHubActionsError("O GitHub devolveu uma resposta de andamento inválida.") from exc
    return [{
        "id": row.get("id"),
        "run_number": row.get("run_number"),
        "display_title": row.get("display_title") or row.get("name"),
        "status": row.get("status"),
        "conclusion": row.get("conclusion"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "html_url": row.get("html_url"),
    } for row in rows]
