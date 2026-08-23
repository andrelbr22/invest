from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from uuid import UUID


# Também permite executar este arquivo diretamente, fora do modo ``python -m``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def normalize_database_url(value: str | None) -> str | None:
    """Normaliza apenas URLs PostgreSQL e rejeita links do painel Neon."""

    clean = str(value or "").strip()
    if not clean:
        return None
    assignment = re.match(r"^(?:DATABASE_ADMIN_URL|DATABASE_URL)\s*=\s*(.+)$", clean, re.IGNORECASE)
    if assignment:
        clean = assignment.group(1).strip()
    markdown = re.match(r"^\[(postgres(?:ql)?(?:\+psycopg)?://[^\]]+)\]\([^)]*\)$", clean)
    if markdown:
        clean = markdown.group(1).strip()
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
    configured = []
    for name in ("DATABASE_ADMIN_URL", "DATABASE_URL"):
        raw = values.get(name)
        if str(raw or "").strip():
            configured.append(name)
        normalized = normalize_database_url(raw)
        if normalized:
            return normalized
    if configured:
        raise SystemExit(
            "Conexão inválida no GitHub: DATABASE_ADMIN_URL/DATABASE_URL deve começar "
            "com postgresql://. Não use o endereço https:// do painel Neon."
        )
    raise SystemExit("DATABASE_ADMIN_URL ou DATABASE_URL não foi configurada nos Secrets do GitHub.")


def main():
    parser = argparse.ArgumentParser(description="Atualiza o catálogo oficial de backtests.")
    parser.add_argument("--tickers", default="", help="Até 100 tickers separados por vírgula; vazio usa o filtro Padrão.")
    parser.add_argument("--max-combinations", type=int, default=200)
    parser.add_argument("--source", choices=("scheduled", "manual"), default="manual")
    parser.add_argument("--job-id", default="", help="Pedido já registrado pelo painel administrativo.")
    parser.add_argument("--validate-database-only", action="store_true")
    args = parser.parse_args()

    database_url = resolve_database_url()
    os.environ["DATABASE_ADMIN_URL"] = database_url
    if args.validate_database_only:
        print("Conexão PostgreSQL reconhecida. A senha e o endereço permaneceram ocultos.")
        return

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session

    from investment_engine.core.backtesting.batch import BacktestBatchService
    from investment_engine.infrastructure.db.session import make_engine

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")

    tickers = [item.strip().upper() for item in args.tickers.replace(";", ",").split(",") if item.strip()]
    with Session(make_engine(database_url)) as session:
        service = BacktestBatchService(session)
        if args.job_id:
            try:
                job = service.get_job(UUID(args.job_id))
            except ValueError as exc:
                raise SystemExit("O identificador do pedido de backtests é inválido.") from exc
            if job is None:
                raise SystemExit("O pedido de backtests não foi encontrado no banco de dados.")
        else:
            job = service.create_job(
                requested_by="github-actions@system.local", source=args.source,
                tickers=tickers or None, max_combinations=args.max_combinations,
            )
            session.commit()
        result = service.run_job(job)
        print(result)


if __name__ == "__main__":
    main()
