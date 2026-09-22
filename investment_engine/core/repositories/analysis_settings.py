from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...infrastructure.db.models import AnalysisColumnSettingORM, ScreeningPresetSettingORM


class AnalysisSettingsRepository:
    """Persist owner alternatives without ever rewriting factory baselines."""

    def __init__(self, session: Session):
        self.session = session

    def get_preset(self, asset_type: str, preset_key: str) -> ScreeningPresetSettingORM | None:
        return self.session.scalar(select(ScreeningPresetSettingORM).where(
            ScreeningPresetSettingORM.asset_type == asset_type,
            ScreeningPresetSettingORM.preset_key == preset_key,
        ))

    def _preset_for_update(self, asset_type: str, preset_key: str) -> ScreeningPresetSettingORM | None:
        return self.session.scalar(select(ScreeningPresetSettingORM).where(
            ScreeningPresetSettingORM.asset_type == asset_type,
            ScreeningPresetSettingORM.preset_key == preset_key,
        ).with_for_update())

    def ensure_preset(
        self,
        *,
        asset_type: str,
        preset_key: str,
        factory_configuration: dict,
        factory_version: str,
    ) -> ScreeningPresetSettingORM:
        row = self.get_preset(asset_type, preset_key)
        if row is not None:
            return row
        row = ScreeningPresetSettingORM(
            asset_type=asset_type,
            preset_key=preset_key,
            factory_version=factory_version,
            factory_configuration_json=factory_configuration,
            owner_configuration_json=None,
            owner_enabled=False,
            revision=1,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_owner_preset(
        self,
        *,
        asset_type: str,
        preset_key: str,
        configuration: dict,
        enabled: bool,
        expected_revision: int,
        actor: str,
    ) -> ScreeningPresetSettingORM:
        row = self._preset_for_update(asset_type, preset_key)
        if row is None:
            raise ValueError("analysis_preset_not_found")
        if int(row.revision) != int(expected_revision):
            raise ValueError("analysis_settings_revision_conflict")
        row.owner_configuration_json = configuration
        row.owner_enabled = bool(enabled)
        row.revision = int(row.revision) + 1
        row.updated_by = str(actor or "").strip().lower()[:320] or None
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def reset_owner_preset(
        self,
        *,
        asset_type: str,
        preset_key: str,
        expected_revision: int,
        actor: str,
    ) -> ScreeningPresetSettingORM:
        row = self._preset_for_update(asset_type, preset_key)
        if row is None:
            raise ValueError("analysis_preset_not_found")
        if int(row.revision) != int(expected_revision):
            raise ValueError("analysis_settings_revision_conflict")
        # Keep the last owner document for recovery/audit. Reset only changes
        # which immutable/mutable variant is effective.
        row.owner_enabled = False
        row.revision = int(row.revision) + 1
        row.updated_by = str(actor or "").strip().lower()[:320] or None
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def get_columns(self, asset_type: str) -> AnalysisColumnSettingORM | None:
        return self.session.scalar(select(AnalysisColumnSettingORM).where(
            AnalysisColumnSettingORM.asset_type == asset_type,
        ))

    def _columns_for_update(self, asset_type: str) -> AnalysisColumnSettingORM | None:
        return self.session.scalar(select(AnalysisColumnSettingORM).where(
            AnalysisColumnSettingORM.asset_type == asset_type,
        ).with_for_update())

    def ensure_columns(self, *, asset_type: str, factory_columns: list[str]) -> AnalysisColumnSettingORM:
        row = self.get_columns(asset_type)
        if row is not None:
            return row
        row = AnalysisColumnSettingORM(
            asset_type=asset_type,
            factory_columns_json=list(factory_columns),
            owner_columns_json=None,
            owner_enabled=False,
            revision=1,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_owner_columns(
        self,
        *,
        asset_type: str,
        columns: list[str],
        enabled: bool,
        expected_revision: int,
        actor: str,
    ) -> AnalysisColumnSettingORM:
        row = self._columns_for_update(asset_type)
        if row is None:
            raise ValueError("analysis_columns_not_found")
        if int(row.revision) != int(expected_revision):
            raise ValueError("analysis_settings_revision_conflict")
        row.owner_columns_json = list(columns)
        row.owner_enabled = bool(enabled)
        row.revision = int(row.revision) + 1
        row.updated_by = str(actor or "").strip().lower()[:320] or None
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row

    def reset_owner_columns(
        self,
        *,
        asset_type: str,
        expected_revision: int,
        actor: str,
    ) -> AnalysisColumnSettingORM:
        row = self._columns_for_update(asset_type)
        if row is None:
            raise ValueError("analysis_columns_not_found")
        if int(row.revision) != int(expected_revision):
            raise ValueError("analysis_settings_revision_conflict")
        row.owner_enabled = False
        row.revision = int(row.revision) + 1
        row.updated_by = str(actor or "").strip().lower()[:320] or None
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return row
