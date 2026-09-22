from __future__ import annotations

from copy import deepcopy
from collections.abc import Callable

from sqlalchemy.orm import Session

from .repositories.analysis_settings import AnalysisSettingsRepository


ANALYSIS_ASSET_TYPES = ("stock", "fii", "etf", "bdr", "future")
SYSTEM_PRESET_KEYS = ("default", "cnpi", "alb")
FACTORY_CONFIGURATION_VERSION = "v1.23.0-r7"

# This catalog validates storage only. It does not hide columns from the
# application: the owner setting controls default visibility and order.
ANALYSIS_COLUMN_CATALOG = {
    "stock": (
        "ticker", "sector", "company_size", "in_ibov", "price", "pe", "pbv", "dy", "roe",
        "graham", "graham_upside", "barsi", "barsi_upside", "relative", "relative_upside",
        "economic", "economic_upside", "alb", "trend_daily", "rsi",
        "s3", "s2", "s1", "pp", "r1", "r2", "r3", "volume_daily", "volume_monthly",
        "best_signal",
    ),
    "fii": (
        "ticker", "segment", "price", "pbv", "dy", "ffo", "vacancy", "barsi",
        "barsi_upside", "relative", "relative_upside", "rsi", "best_signal",
    ),
    "etf": (
        "ticker", "price", "nav", "nav_upside", "premium", "expense", "relative",
        "relative_upside", "rsi", "best_signal",
    ),
    "bdr": (
        "ticker", "sector", "price", "pbv", "relative", "relative_upside", "parity",
        "parity_upside", "rsi", "best_signal",
    ),
    "future": (
        "ticker", "price", "front", "expiry", "spot", "carry", "basis", "rsi", "best_signal",
    ),
}

ANALYSIS_COLUMN_LABELS = {
    "ticker": "Ativo", "sector": "Setor", "segment": "Segmento", "company_size": "Porte",
    "in_ibov": "IBOV", "price": "Preço", "pe": "P/L", "pbv": "P/VP", "dy": "DY",
    "roe": "ROE", "graham": "Número de Graham", "graham_upside": "Potencial Graham",
    "barsi": "Preço-teto DY-alvo", "barsi_upside": "Potencial DY-alvo",
    "relative": "Valor relativo", "relative_upside": "Potencial relativo",
    "economic": "Valor econômico", "economic_upside": "Potencial econômico",
    "alb": "Nota ALB", "trend_daily": "Tendência alta", "rsi": "RSI 14",
    "s3": "S3", "s2": "S2", "s1": "S1", "pp": "Pivô", "r1": "R1", "r2": "R2", "r3": "R3",
    "volume_daily": "Volume/Média 9 diário", "volume_monthly": "Volume/Média 9 mensal",
    "best_signal": "3 melhores backtests", "ffo": "FFO yield", "vacancy": "Vacância",
    "nav": "NAV por cota", "nav_upside": "Desconto/potencial ao NAV",
    "premium": "Prêmio/desconto informado", "expense": "Taxa de administração",
    "parity": "Paridade com o lastro", "parity_upside": "Potencial pela paridade",
    "front": "Contrato frontal", "expiry": "Vencimento", "spot": "Ativo à vista",
    "carry": "Preço teórico", "basis": "Potencial / basis",
}

FACTORY_COLUMN_ORDERS = {
    "stock": ("ticker", "sector", "price", "pe", "pbv", "dy", "roe", "graham_upside", "barsi", "relative", "best_signal"),
    "fii": ("ticker", "segment", "price", "pbv", "dy", "ffo", "vacancy", "barsi", "relative", "best_signal"),
    "etf": ("ticker", "price", "nav", "nav_upside", "premium", "relative", "best_signal"),
    "bdr": ("ticker", "sector", "price", "pbv", "relative", "relative_upside", "best_signal"),
    "future": ("ticker", "price", "front", "expiry", "spot", "carry", "basis", "best_signal"),
}


def validate_analysis_context(asset_type: str, preset_key: str | None = None) -> None:
    if asset_type not in ANALYSIS_ASSET_TYPES:
        raise ValueError("invalid_analysis_asset_type")
    if preset_key is not None and preset_key not in SYSTEM_PRESET_KEYS:
        raise ValueError("analysis_preset_not_found")


def validate_column_order(asset_type: str, values: list[str]) -> list[str]:
    validate_analysis_context(asset_type)
    clean = [str(value).strip() for value in values]
    if not clean:
        raise ValueError("analysis_columns_required")
    if len(clean) != len(set(clean)):
        raise ValueError("analysis_columns_duplicate")
    allowed = set(ANALYSIS_COLUMN_CATALOG[asset_type])
    unknown = [value for value in clean if value not in allowed]
    if unknown:
        raise ValueError(f"analysis_column_unknown:{unknown[0]}")
    if "ticker" not in clean:
        raise ValueError("analysis_ticker_column_required")
    return clean


class AnalysisSettingsService:
    def __init__(
        self,
        session: Session,
        factory_configuration: Callable[[str, str], dict],
    ):
        self.repository = AnalysisSettingsRepository(session)
        self.factory_configuration = factory_configuration

    def _factory(self, asset_type: str, preset_key: str) -> dict:
        validate_analysis_context(asset_type, preset_key)
        return deepcopy(self.factory_configuration(asset_type, preset_key))

    def ensure_defaults(self) -> None:
        for asset_type in ANALYSIS_ASSET_TYPES:
            for preset_key in SYSTEM_PRESET_KEYS:
                self.repository.ensure_preset(
                    asset_type=asset_type,
                    preset_key=preset_key,
                    factory_configuration=self._factory(asset_type, preset_key),
                    factory_version=FACTORY_CONFIGURATION_VERSION,
                )
            self.repository.ensure_columns(
                asset_type=asset_type,
                factory_columns=list(FACTORY_COLUMN_ORDERS[asset_type]),
            )

    def preset_payload(self, asset_type: str, preset_key: str, *, ensure: bool = False) -> dict:
        factory = self._factory(asset_type, preset_key)
        row = self.repository.get_preset(asset_type, preset_key)
        if row is None and ensure:
            row = self.repository.ensure_preset(
                asset_type=asset_type,
                preset_key=preset_key,
                factory_configuration=factory,
                factory_version=FACTORY_CONFIGURATION_VERSION,
            )
        stored_factory = deepcopy(row.factory_configuration_json) if row is not None else factory
        owner = deepcopy(row.owner_configuration_json) if row is not None and row.owner_configuration_json else None
        owner_enabled = bool(row is not None and row.owner_enabled and owner is not None)
        effective = deepcopy(owner if owner_enabled else stored_factory)
        return {
            "asset_type": asset_type,
            "preset_id": preset_key,
            "factory_version": row.factory_version if row is not None else FACTORY_CONFIGURATION_VERSION,
            "factory_configuration": stored_factory,
            "owner_configuration": owner,
            "owner_enabled": owner_enabled,
            "active_variant": "owner" if owner_enabled else "factory",
            "configuration": effective,
            "revision": int(row.revision) if row is not None else 0,
            "updated_by": row.updated_by if row is not None else None,
            "updated_at": row.updated_at if row is not None else None,
        }

    def update_preset(
        self,
        asset_type: str,
        preset_key: str,
        *,
        configuration: dict,
        enabled: bool,
        expected_revision: int,
        actor: str,
    ) -> dict:
        self.repository.ensure_preset(
            asset_type=asset_type,
            preset_key=preset_key,
            factory_configuration=self._factory(asset_type, preset_key),
            factory_version=FACTORY_CONFIGURATION_VERSION,
        )
        self.repository.update_owner_preset(
            asset_type=asset_type,
            preset_key=preset_key,
            configuration=deepcopy(configuration),
            enabled=enabled,
            expected_revision=expected_revision,
            actor=actor,
        )
        return self.preset_payload(asset_type, preset_key)

    def reset_preset(
        self,
        asset_type: str,
        preset_key: str,
        *,
        expected_revision: int,
        actor: str,
    ) -> dict:
        validate_analysis_context(asset_type, preset_key)
        self.repository.reset_owner_preset(
            asset_type=asset_type,
            preset_key=preset_key,
            expected_revision=expected_revision,
            actor=actor,
        )
        return self.preset_payload(asset_type, preset_key)

    def columns_payload(self, asset_type: str, *, ensure: bool = False) -> dict:
        validate_analysis_context(asset_type)
        factory = list(FACTORY_COLUMN_ORDERS[asset_type])
        row = self.repository.get_columns(asset_type)
        if row is None and ensure:
            row = self.repository.ensure_columns(asset_type=asset_type, factory_columns=factory)
        stored_factory = list(row.factory_columns_json) if row is not None else factory
        owner = list(row.owner_columns_json) if row is not None and row.owner_columns_json else None
        owner_enabled = bool(row is not None and row.owner_enabled and owner is not None)
        return {
            "asset_type": asset_type,
            "available_columns": [
                {"id": column_id, "label": ANALYSIS_COLUMN_LABELS[column_id], "always": column_id == "ticker"}
                for column_id in ANALYSIS_COLUMN_CATALOG[asset_type]
            ],
            "factory_columns": stored_factory,
            "owner_columns": owner,
            "owner_enabled": owner_enabled,
            "active_variant": "owner" if owner_enabled else "factory",
            "columns": list(owner if owner_enabled else stored_factory),
            "revision": int(row.revision) if row is not None else 0,
            "updated_by": row.updated_by if row is not None else None,
            "updated_at": row.updated_at if row is not None else None,
        }

    def update_columns(
        self,
        asset_type: str,
        *,
        columns: list[str],
        enabled: bool,
        expected_revision: int,
        actor: str,
    ) -> dict:
        clean = validate_column_order(asset_type, columns)
        self.repository.ensure_columns(
            asset_type=asset_type,
            factory_columns=list(FACTORY_COLUMN_ORDERS[asset_type]),
        )
        self.repository.update_owner_columns(
            asset_type=asset_type,
            columns=clean,
            enabled=enabled,
            expected_revision=expected_revision,
            actor=actor,
        )
        return self.columns_payload(asset_type)

    def reset_columns(self, asset_type: str, *, expected_revision: int, actor: str) -> dict:
        validate_analysis_context(asset_type)
        self.repository.reset_owner_columns(
            asset_type=asset_type,
            expected_revision=expected_revision,
            actor=actor,
        )
        return self.columns_payload(asset_type)

    def admin_payload(self) -> dict:
        self.ensure_defaults()
        return {
            "factory_version": FACTORY_CONFIGURATION_VERSION,
            "presets": [
                self.preset_payload(asset_type, preset_key)
                for asset_type in ANALYSIS_ASSET_TYPES
                for preset_key in SYSTEM_PRESET_KEYS
            ],
            "columns": [self.columns_payload(asset_type) for asset_type in ANALYSIS_ASSET_TYPES],
        }
