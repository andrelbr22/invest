from __future__ import annotations

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="Atualiza o catálogo oficial de backtests.")
    parser.add_argument("--tickers", default="", help="Até 100 tickers separados por vírgula; vazio usa o filtro Padrão.")
    parser.add_argument("--max-combinations", type=int, default=200)
    parser.add_argument("--source", choices=("scheduled", "manual"), default="manual")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_ADMIN_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_ADMIN_URL ou DATABASE_URL não foi configurada.")
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    os.environ["DATABASE_ADMIN_URL"] = database_url

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session

    from investment_engine.core.backtesting.batch import BacktestBatchService
    from investment_engine.infrastructure.db.session import make_engine

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    tickers = [item.strip().upper() for item in args.tickers.replace(";", ",").split(",") if item.strip()]
    with Session(make_engine(database_url)) as session:
        service = BacktestBatchService(session)
        job = service.create_job(
            requested_by="github-actions@system.local", source=args.source,
            tickers=tickers or None, max_combinations=args.max_combinations,
        )
        session.commit()
        result = service.run_job(job)
        print(result)


if __name__ == "__main__":
    main()
