from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from investment_engine.infrastructure.db.models import OperationalArchiveORM
from investment_engine.infrastructure.db.session import get_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export immutable operational archive rows as JSON Lines to standard output.",
    )
    parser.add_argument("--entity-type", default="")
    parser.add_argument("--limit", type=int, default=100000)
    args = parser.parse_args()

    statement = select(OperationalArchiveORM).order_by(
        OperationalArchiveORM.archived_at,
        OperationalArchiveORM.id,
    ).limit(max(1, min(1000000, int(args.limit))))
    if args.entity_type:
        statement = statement.where(
            OperationalArchiveORM.entity_type == args.entity_type.strip(),
        )

    session = get_session_factory()()
    try:
        for row in session.scalars(statement).yield_per(500):
            print(json.dumps({
                "entity_type": row.entity_type,
                "source_id": row.source_id,
                "source_created_at": row.source_created_at,
                "source_updated_at": row.source_updated_at,
                "archived_at": row.archived_at,
                "schema_version": row.schema_version,
                "checksum": row.checksum,
                "record": row.record_json,
            }, ensure_ascii=False, sort_keys=True, default=str))
    finally:
        session.close()


if __name__ == "__main__":
    main()
