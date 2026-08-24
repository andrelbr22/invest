"""Remove legacy duplicate Graham snapshots created by V1.2.

Keeps current/future Graham versions and all other valuation methods.
Safe to run more than once.
"""
from sqlalchemy import delete, select, func
from investment_engine.infrastructure.db.session import get_session_factory
from investment_engine.infrastructure.db.models import ValuationSnapshotORM

LEGACY_GRAHAM_VERSIONS = ("1.2",)

s = get_session_factory()()
try:
    before = s.scalar(
        select(func.count()).select_from(ValuationSnapshotORM).where(
            ValuationSnapshotORM.method == "graham_number",
            ValuationSnapshotORM.method_version.in_(LEGACY_GRAHAM_VERSIONS),
        )
    ) or 0
    s.execute(
        delete(ValuationSnapshotORM).where(
            ValuationSnapshotORM.method == "graham_number",
            ValuationSnapshotORM.method_version.in_(LEGACY_GRAHAM_VERSIONS),
        )
    )
    s.commit()
    print(f"Valuation cleanup: {before} registro(s) legado(s) de Graham removido(s).")
finally:
    s.close()
