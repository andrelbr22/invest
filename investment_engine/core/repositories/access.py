from __future__ import annotations

from datetime import datetime, timezone
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import AccessLevelORM, UserAccessPolicyORM


PERMISSION_FIELDS = (
    "can_view_market",
    "can_use_advanced_filters",
    "can_use_fdi_analysis",
    "can_use_alb_analysis",
    "can_use_graham_valuation",
    "can_use_dividend_ceiling",
    "can_use_relative_valuation",
    "can_use_economic_valuation",
    "can_view_portfolio",
    "can_write_portfolio",
    "can_view_finances",
    "can_write_finances",
    "can_view_backtests",
    "can_run_backtests",
    "can_refresh_backtest_signals",
    "can_view_backtest_studies",
    "can_view_news_insights",
    "can_use_price_alerts",
    "can_alert_price_above",
    "can_alert_price_below",
    "can_alert_change_positive",
    "can_alert_change_negative",
    "can_sync_market",
    "can_manage_users",
)

LIMIT_FIELDS = (
    "custom_filter_limit",
    "alert_asset_limit",
    "backtest_asset_limit",
    "backtest_daily_limit",
    "backtest_strategy_limit",
    "backtest_cooldown_seconds",
)

ACCESS_RULE_FIELDS = (*PERMISSION_FIELDS, *LIMIT_FIELDS)
ALERT_ASSET_LIMITS = {0, 1, 3, 5, 10}
BACKTEST_ASSET_LIMITS = {0, 1, 3, 5, 10}
BACKTEST_DAILY_LIMITS = {0, 1, 5, 10, 20}
BACKTEST_STRATEGY_LIMITS = {0, 1, 2, 3, 5}
ACCESS_LEVEL_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


def _tier(
    name: str,
    description: str,
    sort_order: int,
    enabled: tuple[str, ...] = (),
    **limits: int,
) -> dict:
    return {
        "name": name,
        "description": description,
        "sort_order": sort_order,
        "is_system": True,
        "is_active": True,
        **{field: field in enabled for field in PERMISSION_FIELDS},
        "custom_filter_limit": 0,
        "alert_asset_limit": 0,
        "backtest_asset_limit": 0,
        "backtest_daily_limit": 0,
        "backtest_strategy_limit": 0,
        "backtest_cooldown_seconds": 60,
        **limits,
    }


_BASIC_PERMISSIONS = (
    "can_view_market", "can_use_advanced_filters",
    "can_view_portfolio", "can_write_portfolio", "can_view_backtests",
    "can_run_backtests", "can_view_news_insights", "can_use_price_alerts",
    "can_alert_price_above", "can_alert_price_below",
    "can_alert_change_positive", "can_alert_change_negative",
)
_MEMBER_PERMISSIONS = (
    *_BASIC_PERMISSIONS,
    "can_use_fdi_analysis", "can_use_graham_valuation", "can_use_dividend_ceiling",
    "can_view_finances", "can_write_finances",
    "can_refresh_backtest_signals", "can_view_backtest_studies",
)
_VIP_PERMISSIONS = tuple(field for field in PERMISSION_FIELDS if field not in {"can_sync_market", "can_manage_users"})


DEFAULT_ACCESS_LEVELS = {
    "guest": _tier(
        "Convidado",
        "Consulta o Painel de Mercado, sem recursos privados ou gravações.",
        10,
        ("can_view_market",),
    ),
    "basic": _tier(
        "Acesso básico",
        "Recursos essenciais com limites reduzidos para filtros, carteira, alertas e backtests.",
        20,
        _BASIC_PERMISSIONS,
        custom_filter_limit=1,
        alert_asset_limit=1,
        backtest_asset_limit=1,
        backtest_daily_limit=1,
        backtest_strategy_limit=1,
    ),
    "member": _tier(
        "Membro",
        "Análises, carteira, finanças, alertas e backtests com limites intermediários.",
        30,
        _MEMBER_PERMISSIONS,
        custom_filter_limit=2,
        alert_asset_limit=3,
        backtest_asset_limit=3,
        backtest_daily_limit=5,
        backtest_strategy_limit=2,
    ),
    "vip": _tier(
        "Membro VIP",
        "Todos os recursos de investimento e os maiores limites de uso.",
        40,
        _VIP_PERMISSIONS,
        custom_filter_limit=3,
        alert_asset_limit=10,
        backtest_asset_limit=10,
        backtest_daily_limit=20,
        backtest_strategy_limit=5,
    ),
    "owner": _tier(
        "Proprietário",
        "Acesso permanente e integral à plataforma e à administração.",
        1000,
        PERMISSION_FIELDS,
        custom_filter_limit=3,
        alert_asset_limit=10,
        backtest_asset_limit=10,
        backtest_daily_limit=20,
        backtest_strategy_limit=5,
    ),
}


def normalized_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def normalized_level_slug(slug: str | None) -> str:
    clean = str(slug or "").strip().lower()
    if not ACCESS_LEVEL_SLUG_PATTERN.fullmatch(clean):
        raise ValueError("invalid_access_level_slug")
    return clean


def _limit_value(field: str, value) -> int:
    number = int(value or 0)
    allowed = {
        "alert_asset_limit": ALERT_ASSET_LIMITS,
        "backtest_asset_limit": BACKTEST_ASSET_LIMITS,
        "backtest_daily_limit": BACKTEST_DAILY_LIMITS,
        "backtest_strategy_limit": BACKTEST_STRATEGY_LIMITS,
    }
    if field == "custom_filter_limit":
        if number not in {0, 1, 2, 3}:
            raise ValueError("invalid_custom_filter_limit")
        return number
    if field == "backtest_cooldown_seconds":
        if not 60 <= number <= 3600:
            raise ValueError("invalid_backtest_cooldown_seconds")
        return number
    if number not in allowed[field]:
        raise ValueError(f"invalid_{field}")
    return number


def validate_access_rules(values: dict | None, *, partial: bool = True) -> dict:
    """Validate a reusable level or per-user override without accepting arbitrary fields."""
    supplied = dict(values or {})
    unknown = sorted(set(supplied) - set(ACCESS_RULE_FIELDS))
    if unknown:
        raise ValueError(f"unknown_access_rule:{unknown[0]}")
    clean = {}
    for field, value in supplied.items():
        if field in PERMISSION_FIELDS:
            if not isinstance(value, bool):
                raise ValueError(f"invalid_{field}")
            clean[field] = value
        else:
            clean[field] = _limit_value(field, value)
    if not partial:
        for field in PERMISSION_FIELDS:
            clean.setdefault(field, False)
        for field in LIMIT_FIELDS:
            clean.setdefault(field, 60 if field == "backtest_cooldown_seconds" else 0)
    return clean


def _rules_from(source) -> dict:
    permissions = {}
    for field in PERMISSION_FIELDS:
        value = getattr(source, field, None)
        # SQLAlchemy applies Python column defaults during INSERT.  Repository
        # helpers are also used with transient rows in validation and tests, so
        # mirror the one permissive model default before the row is flushed.
        permissions[field] = bool(field == "can_view_market" if value is None else value)
    limits = {}
    for field in LIMIT_FIELDS:
        value = getattr(source, field, None)
        if value is None:
            value = 60 if field == "backtest_cooldown_seconds" else 0
        limits[field] = int(value)
    return {
        **permissions,
        **limits,
    }


def apply_access_dependencies(values: dict) -> dict:
    """Return a coherent effective policy, failing closed when a parent capability is off."""
    result = validate_access_rules(values, partial=False)
    if result["can_use_alb_analysis"]:
        result["can_use_graham_valuation"] = True
        result["can_use_dividend_ceiling"] = True
        result["can_use_relative_valuation"] = True
        result["can_use_economic_valuation"] = True
    if not result["can_view_market"]:
        for field in (
            "can_use_advanced_filters", "can_use_fdi_analysis", "can_use_alb_analysis",
            "can_use_graham_valuation", "can_use_dividend_ceiling",
            "can_use_relative_valuation", "can_use_economic_valuation", "can_sync_market",
        ):
            result[field] = False
        result["custom_filter_limit"] = 0
    if not result["can_view_portfolio"]:
        result["can_write_portfolio"] = False
        result["can_view_news_insights"] = False
        result["can_use_price_alerts"] = False
    if not result["can_view_finances"]:
        result["can_write_finances"] = False
    if not result["can_view_backtests"]:
        result["can_run_backtests"] = False
        result["can_refresh_backtest_signals"] = False
        result["can_view_backtest_studies"] = False
    if not result["can_run_backtests"]:
        result["backtest_asset_limit"] = 0
        result["backtest_daily_limit"] = 0
        result["backtest_strategy_limit"] = 0
    if not result["can_use_price_alerts"] or result["alert_asset_limit"] == 0:
        result["can_use_price_alerts"] = False
        result["alert_asset_limit"] = 0
        result["can_alert_price_above"] = False
        result["can_alert_price_below"] = False
        result["can_alert_change_positive"] = False
        result["can_alert_change_negative"] = False
    result["backtest_cooldown_seconds"] = max(60, result["backtest_cooldown_seconds"])
    return result


def full_owner_policy(email: str, display_name: str | None = None) -> dict:
    return {
        "email": normalized_email(email),
        "display_name": display_name,
        "role": "owner",
        "status": "approved",
        **{field: True for field in PERMISSION_FIELDS},
        "custom_filter_limit": 3,
        "alert_asset_limit": 10,
        "backtest_asset_limit": 10,
        "backtest_daily_limit": 20,
        "backtest_strategy_limit": 5,
        "backtest_cooldown_seconds": 60,
        "access_level_slug": "owner",
        "access_level_name": "Proprietário",
        "access_inheritance": True,
        "access_overrides": {},
        "is_owner": True,
    }


def access_level_dict(row: AccessLevelORM, *, member_count: int | None = None) -> dict:
    rules = apply_access_dependencies(_rules_from(row))
    result = {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_system": bool(row.is_system),
        "is_active": bool(row.is_active),
        "sort_order": int(row.sort_order or 0),
        "permissions": {field: rules[field] for field in PERMISSION_FIELDS},
        "limits": {field: rules[field] for field in LIMIT_FIELDS},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if member_count is not None:
        result["member_count"] = int(member_count)
    return result


def policy_dict(row: UserAccessPolicyORM, *, is_owner: bool = False) -> dict:
    if is_owner:
        return full_owner_policy(row.email, row.display_name)
    level = getattr(row, "access_level", None)
    inherited = level is not None
    rules = _rules_from(level or row)
    overrides = {}
    if inherited:
        try:
            overrides = validate_access_rules(getattr(row, "access_overrides_json", None) or {}, partial=True)
        except ValueError:
            # A malformed historical override must never broaden access.
            overrides = {}
        rules.update(overrides)
    rules = apply_access_dependencies(rules)
    blocked = row.status == "blocked"
    if blocked:
        for field in PERMISSION_FIELDS:
            rules[field] = False
        for field in LIMIT_FIELDS:
            rules[field] = 60 if field == "backtest_cooldown_seconds" else 0
    return {
        "email": row.email,
        "display_name": row.display_name,
        "role": level.slug if level is not None else row.role,
        "status": row.status,
        **rules,
        "access_level_slug": level.slug if level is not None else None,
        "access_level_name": level.name if level is not None else None,
        "access_inheritance": inherited,
        "access_overrides": overrides,
        "is_owner": False,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_seen_at": row.last_seen_at,
    }


class AccessLevelRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, slug: str) -> AccessLevelORM | None:
        clean = normalized_level_slug(slug)
        return self.session.scalar(select(AccessLevelORM).where(AccessLevelORM.slug == clean))

    def list_all(self, *, include_inactive: bool = True) -> list[AccessLevelORM]:
        query = select(AccessLevelORM)
        if not include_inactive:
            query = query.where(AccessLevelORM.is_active.is_(True))
        return list(self.session.scalars(query.order_by(AccessLevelORM.sort_order, AccessLevelORM.name)))

    def member_count(self, level_id) -> int:
        return int(self.session.scalar(
            select(func.count()).select_from(UserAccessPolicyORM)
            .where(UserAccessPolicyORM.access_level_id == level_id)
        ) or 0)

    def members(self, level_id) -> list[UserAccessPolicyORM]:
        return list(self.session.scalars(
            select(UserAccessPolicyORM)
            .where(UserAccessPolicyORM.access_level_id == level_id)
            .order_by(UserAccessPolicyORM.email)
        ))

    def create(
        self,
        *,
        slug: str,
        name: str,
        description: str | None = None,
        is_active: bool = True,
        sort_order: int = 100,
        rules: dict | None = None,
    ) -> AccessLevelORM:
        clean = normalized_level_slug(slug)
        if clean == "owner":
            raise ValueError("owner_access_level_is_permanent")
        if self.get(clean) is not None:
            raise ValueError("access_level_already_exists")
        values = apply_access_dependencies(validate_access_rules(rules, partial=False))
        row = AccessLevelORM(
            slug=clean,
            name=str(name or "").strip()[:80],
            description=str(description or "").strip()[:500] or None,
            is_system=False,
            is_active=bool(is_active),
            sort_order=max(0, min(10000, int(sort_order))),
            **values,
        )
        if not row.name:
            raise ValueError("access_level_name_required")
        self.session.add(row)
        self.session.flush()
        return row

    def update(self, slug: str, **changes) -> AccessLevelORM | None:
        row = self.get(slug)
        if row is None:
            return None
        if row.slug == "owner":
            raise ValueError("owner_access_level_is_permanent")
        if "name" in changes and changes["name"] is not None:
            name = str(changes["name"]).strip()[:80]
            if not name:
                raise ValueError("access_level_name_required")
            row.name = name
        if "description" in changes:
            row.description = str(changes["description"] or "").strip()[:500] or None
        if "is_active" in changes and changes["is_active"] is not None:
            row.is_active = bool(changes["is_active"])
        if "sort_order" in changes and changes["sort_order"] is not None:
            row.sort_order = max(0, min(10000, int(changes["sort_order"])))
        rules = validate_access_rules(changes.get("rules") or {}, partial=True)
        current = _rules_from(row)
        current.update(rules)
        for field, value in apply_access_dependencies(current).items():
            setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row


class AccessPolicyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, email: str) -> UserAccessPolicyORM | None:
        clean = normalized_email(email)
        if not clean:
            return None
        return self.session.scalar(select(UserAccessPolicyORM).where(UserAccessPolicyORM.email == clean))

    def register(self, email: str, display_name: str | None = None, *, is_owner: bool = False) -> UserAccessPolicyORM:
        clean = normalized_email(email)
        if not clean:
            raise ValueError("email_required")
        row = self.get(clean)
        now = datetime.now(timezone.utc)
        if row is None:
            guest = self.session.scalar(select(AccessLevelORM).where(AccessLevelORM.slug == "guest"))
            row = UserAccessPolicyORM(
                email=clean,
                display_name=display_name,
                last_seen_at=now,
                access_level=guest,
                role="guest" if guest is not None else "visitor",
            )
            self.session.add(row)
        elif display_name:
            row.display_name = display_name
        row.last_seen_at = now
        if is_owner:
            owner_level = self.session.scalar(select(AccessLevelORM).where(AccessLevelORM.slug == "owner"))
            row.access_level = owner_level
            row.access_overrides_json = {}
            row.role = "owner"
            row.status = "approved"
            for field in PERMISSION_FIELDS:
                setattr(row, field, True)
            row.custom_filter_limit = 3
            row.alert_asset_limit = 10
            row.backtest_asset_limit = 10
            row.backtest_daily_limit = 20
            row.backtest_strategy_limit = 5
            row.backtest_cooldown_seconds = 60
        self.session.flush()
        return row

    def list_all(self) -> list[UserAccessPolicyORM]:
        return list(self.session.scalars(select(UserAccessPolicyORM).order_by(UserAccessPolicyORM.email)))

    def list_page(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        level_slug: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[UserAccessPolicyORM], int]:
        statement = select(UserAccessPolicyORM).outerjoin(UserAccessPolicyORM.access_level)
        term = str(query or "").strip()
        if term:
            pattern = f"%{term}%"
            statement = statement.where(or_(
                UserAccessPolicyORM.email.ilike(pattern),
                UserAccessPolicyORM.display_name.ilike(pattern),
            ))
        if status:
            statement = statement.where(UserAccessPolicyORM.status == str(status).strip().lower())
        if level_slug == "legacy":
            statement = statement.where(UserAccessPolicyORM.access_level_id.is_(None))
        elif level_slug:
            statement = statement.where(AccessLevelORM.slug == str(level_slug).strip().lower())
        total = int(self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ) or 0)
        rows = list(self.session.scalars(
            statement.order_by(UserAccessPolicyORM.last_seen_at.desc(), UserAccessPolicyORM.email)
            .offset(max(0, int(offset))).limit(max(1, min(200, int(limit))))
        ))
        return rows, total

    def assign_level(
        self,
        email: str,
        level: AccessLevelORM,
        *,
        clear_overrides: bool = True,
    ) -> UserAccessPolicyORM | None:
        row = self.get(email)
        if row is None:
            return None
        if row.role == "owner" or level.slug == "owner":
            raise ValueError("owner_permissions_are_permanent")
        if not level.is_active:
            raise ValueError("access_level_is_inactive")
        row.access_level = level
        row.role = level.slug
        if clear_overrides:
            row.access_overrides_json = {}
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def set_overrides(self, email: str, overrides: dict, *, replace: bool = True) -> UserAccessPolicyORM | None:
        row = self.get(email)
        if row is None:
            return None
        if row.role == "owner":
            raise ValueError("owner_permissions_are_permanent")
        if row.access_level_id is None:
            raise ValueError("access_level_required_for_overrides")
        clean = validate_access_rules(overrides, partial=True)
        current = {} if replace else dict(row.access_overrides_json or {})
        current.update(clean)
        row.access_overrides_json = current
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def clear_overrides(self, email: str) -> UserAccessPolicyORM | None:
        row = self.get(email)
        if row is None:
            return None
        if row.role == "owner":
            raise ValueError("owner_permissions_are_permanent")
        row.access_overrides_json = {}
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def update(self, email: str, **changes) -> UserAccessPolicyORM | None:
        row = self.get(email)
        if row is None:
            return None
        rule_changes = {
            field: changes[field]
            for field in ACCESS_RULE_FIELDS
            if field in changes and changes[field] is not None
        }
        if rule_changes and row.access_level_id is not None:
            current = dict(row.access_overrides_json or {})
            current.update(validate_access_rules(rule_changes, partial=True))
            row.access_overrides_json = current
        for field in ("display_name", "role", "status"):
            if field in changes and changes[field] is not None:
                setattr(row, field, changes[field])
        if row.access_level_id is None and rule_changes:
            # Legacy rows keep their physical permission columns. Apply the
            # same dependency rules used by inherited levels so an ALB grant,
            # parent revocation or limit change cannot leave contradictory
            # values behind.
            current = _rules_from(row)
            current.update(validate_access_rules(rule_changes, partial=True))
            for field, value in apply_access_dependencies(current).items():
                setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row
