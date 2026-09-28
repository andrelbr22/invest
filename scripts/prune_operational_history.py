from __future__ import annotations

import argparse
import json

from investment_engine.core.jobs.retention import OperationalRetentionService
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.session import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or apply the checksum-protected operational retention policy.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Archive eligible rows and remove them from hot tables. Without this flag it is a dry run.",
    )
    parser.add_argument("--limit", type=int, default=settings.operational_retention_batch_size)
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        result = OperationalRetentionService(session).run(
            apply=bool(args.apply),
            job_retention_days=settings.background_job_retention_days,
            operational_retention_days=settings.operational_retention_days,
            limit=args.limit,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
