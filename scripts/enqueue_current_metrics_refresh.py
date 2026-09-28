from __future__ import annotations

"""Queue the resumable current-metrics materializer for a release.

This command only writes one small queue row. The worker performs the heavy
historical reads and technical calculations after the web process is healthy.
"""

import argparse
from datetime import datetime, timezone
import os

from investment_engine.core.repositories.background_jobs import BackgroundJobRepository
from investment_engine.infrastructure.config import settings
from investment_engine.infrastructure.db.session import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requested-by", default="system:release")
    parser.add_argument("--commit", default=os.getenv("APP_COMMIT_SHA", "unknown"))
    parser.add_argument(
        "--batch-size", type=int,
        default=settings.current_metrics_backfill_batch_size,
    )
    args = parser.parse_args()

    commit = str(args.commit or "unknown").strip()
    cycle = f"release:{commit}"
    batch_size = max(1, min(1000, int(args.batch_size)))
    session = get_session_factory()()
    try:
        job, created = BackgroundJobRepository(session).enqueue(
            "current_metrics_refresh",
            {
                "snapshot_key": "market:current-metrics",
                "after_ticker": "",
                "batch_size": batch_size,
                "cycle": cycle,
                "trigger": "release",
                "requested_by": str(args.requested_by or "system:release"),
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
            priority=146,
            max_attempts=3,
            deduplication_key=f"current-metrics:{cycle}:start",
            idempotency_key=f"current-metrics:{cycle}:start",
        )
        session.commit()
        print(
            f"current_metrics_job={job.id} "
            f"created={str(created).lower()} cycle={cycle}"
        )
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
