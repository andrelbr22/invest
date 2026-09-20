from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def normalize_database_url(value: str | None) -> str | None:
    """Normalize the temporary PostgreSQL URL used only inside GitHub Actions."""

    clean = str(value or "").strip()
    if not clean:
        return None
    assignment = re.match(r"^(?:DATABASE_ADMIN_URL|DATABASE_URL)\s*=\s*(.+)$", clean, re.IGNORECASE)
    if assignment:
        clean = assignment.group(1).strip()
    clean = clean.strip().strip('"').strip("'").strip()
    if clean.startswith("postgresql+psycopg://"):
        return clean
    if clean.startswith("postgresql://"):
        return clean.replace("postgresql://", "postgresql+psycopg://", 1)
    if clean.startswith("postgres://"):
        return clean.replace("postgres://", "postgresql+psycopg://", 1)
    return None


def resolve_database_url(environment: dict | None = None) -> str:
    values = environment if environment is not None else os.environ
    normalized = normalize_database_url(values.get("DATABASE_URL"))
    if normalized:
        return normalized
    raise SystemExit("O PostgreSQL temporário do GitHub Actions não foi iniciado corretamente.")


def prepare_calculation_database(database_url: str, environment: dict | None = None):
    """Create the disposable CI schema without replaying production history.

    The weekly calculation database contains no user data and exists only for
    the duration of one GitHub Actions job.  Building the current SQLAlchemy
    schema directly avoids coupling this worker to old production migrations.
    The explicit flag and local database checks prevent accidental use against
    a persistent database.
    """

    values = environment if environment is not None else os.environ
    ephemeral = str(values.get("BACKTEST_EPHEMERAL_DATABASE") or "").strip().lower()
    if ephemeral not in {"1", "true", "yes", "on"}:
        raise SystemExit("O banco descartável dos backtests não foi confirmado pelo workflow.")

    from sqlalchemy.engine import make_url

    parsed = make_url(database_url)
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.database != "backtests_ci":
        raise SystemExit("O banco informado não é o PostgreSQL descartável dos backtests.")

    from investment_engine.infrastructure.db import models  # noqa: F401
    from investment_engine.infrastructure.db.base import Base
    from investment_engine.infrastructure.db.session import make_engine

    engine = make_engine(database_url)
    Base.metadata.create_all(bind=engine)
    return engine


def _tickers(value: str) -> list[str]:
    clean = []
    for item in str(value or "").replace(";", ",").split(","):
        ticker = item.strip().upper()
        if ticker and ticker not in clean:
            clean.append(ticker)
    return clean[:100]


def main():
    parser = argparse.ArgumentParser(description="Calcula no GitHub e entrega o catálogo oficial à Oracle.")
    parser.add_argument("--tickers", default="", help="Até 100 tickers separados por vírgula.")
    parser.add_argument("--max-combinations", type=int, default=200)
    parser.add_argument("--source", choices=("scheduled", "manual"), default="manual")
    parser.add_argument("--job-id", default="", help="Pedido já registrado pelo painel administrativo.")
    args = parser.parse_args()

    from sqlalchemy.orm import Session

    from investment_engine.core.backtesting.batch import BacktestBatchService
    from investment_engine.integrations.backtest_delivery import (
        BacktestDeliveryClient,
        BacktestDeliveryError,
    )

    database_url = resolve_database_url()
    failure_stage = "start_callback"
    failure_ticker: str | None = None
    callback = BacktestDeliveryClient(
        base_url=os.getenv("BACKTEST_CALLBACK_URL", ""),
        token=os.getenv("BACKTEST_CALLBACK_TOKEN", ""),
    )
    requested_job_id = str(args.job_id or "").strip() or None
    remote_job_id: str | None = None
    try:
        remote = callback.start_job(
            source=args.source,
            max_combinations=args.max_combinations,
            job_id=requested_job_id,
            tickers=_tickers(args.tickers),
        )
        remote_job_id = str(remote.get("id") or "").strip()
        if not remote_job_id:
            raise BacktestDeliveryError("A Oracle não informou o identificador do pedido.")
        if remote.get("status") in {"completed", "completed_with_errors"}:
            print(f"Pedido {remote_job_id[:8]} já estava concluído. Nenhum cálculo foi repetido.")
            return
        pending = list(remote.get("pending_tickers") or remote.get("tickers") or [])
        if not pending:
            callback.finish_job(remote_job_id)
            print(f"Pedido {remote_job_id[:8]} concluído sem ativos pendentes.")
            return

        failure_stage = "prepare_temporary_database"
        engine = prepare_calculation_database(database_url)

        failure_stage = "prepare_local_job"
        with Session(engine) as session:
            service = BacktestBatchService(session)
            local_job = service.create_job(
                requested_by="github-actions@system.local",
                source=args.source,
                tickers=pending,
                max_combinations=args.max_combinations,
                job_id=UUID(remote_job_id),
            )
            session.commit()

            def deliver(payload: dict):
                nonlocal failure_stage, failure_ticker
                failure_stage = "deliver_asset"
                failure_ticker = str(payload.get("ticker") or "").strip().upper() or None
                result = callback.deliver_asset(remote_job_id, payload)
                imported = result.get("imported_runs", 0)
                skipped = result.get("skipped_runs", 0)
                chunks = result.get("chunks_sent", 1)
                print(
                    f"{payload['ticker']}: entregue com segurança "
                    f"em {chunks} pacote(s) "
                    f"({imported} novo(s), {skipped} já existente(s))."
                )

            failure_stage = "calculate_assets"
            service.run_job(local_job, asset_callback=deliver)
        failure_stage = "finish_callback"
        final = callback.finish_job(remote_job_id)
        print(
            f"Pedido {remote_job_id[:8]} finalizado: "
            f"{final.get('completed_runs', 0)} concluído(s), "
            f"{final.get('failed_runs', 0)} falha(s)."
        )
    except Exception as exc:
        if remote_job_id:
            try:
                callback.fail_job(
                    remote_job_id,
                    code="github_worker_failed",
                    message="A execução no GitHub foi interrompida antes da conclusão.",
                    details={
                        "exception_type": type(exc).__name__,
                        "failure_stage": failure_stage,
                        "ticker": failure_ticker,
                        "safe_message": str(exc)[:240],
                    },
                )
            except Exception:
                pass
        if isinstance(exc, (BacktestDeliveryError, SystemExit)):
            raise
        raise SystemExit(
            f"Falha segura na etapa {failure_stage}: {type(exc).__name__}"
        ) from exc


if __name__ == "__main__":
    main()
