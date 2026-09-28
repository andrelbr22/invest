from __future__ import annotations

import argparse
import json

from investment_engine.core.jobs.retention import OperationalRetentionService
from investment_engine.infrastructure.db.session import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the checksum of immutable operational archive rows.",
    )
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        result = OperationalRetentionService(session).verify_archive(limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if not result["valid"]:
            raise SystemExit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
