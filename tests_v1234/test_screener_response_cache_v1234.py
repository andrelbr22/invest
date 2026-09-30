import importlib


api_module = importlib.import_module("investment_engine.api.app")


class _FakeSession:
    def __init__(self):
        self.bind = object()

    def get_bind(self):
        return self.bind


def _access(**changes):
    payload = {
        "email": "member@example.com",
        "can_view_market": True,
        "can_use_alb_analysis": False,
        "can_use_graham_valuation": True,
        "can_use_dividend_ceiling": True,
        "can_use_relative_valuation": True,
        "can_use_economic_valuation": True,
    }
    payload.update(changes)
    return payload


def test_system_screener_cache_reuses_page_and_separates_access(monkeypatch):
    calls = {"screen": 0}

    class FakeRepository:
        def __init__(self, _db):
            pass

        def screen_latest_stocks(self, _filters, *, limit, offset):
            calls["screen"] += 1
            assert limit == 50
            assert offset == 0
            return []

    setting = {
        "active_variant": "factory",
        "revision": 4,
        "factory_version": "1",
        "configuration": {},
    }
    monkeypatch.setattr(api_module, "AssetRepository", FakeRepository)
    monkeypatch.setattr(
        api_module,
        "_cached_analysis_preset_payload",
        lambda _db, _asset_type, _strategy_id: dict(setting),
    )
    api_module._SCREENER_RESPONSE_CACHE.invalidate()
    session = _FakeSession()

    try:
        first = api_module.screen_db_stocks(
            "default", limit=50, offset=0, access=_access(), db=session,
        )
        second = api_module.screen_db_stocks(
            "default", limit=50, offset=0, access=_access(), db=session,
        )
        assert first == second == []
        assert calls["screen"] == 1

        api_module.screen_db_stocks(
            "default",
            limit=50,
            offset=0,
            access=_access(can_use_relative_valuation=False),
            db=session,
        )
        assert calls["screen"] == 2

        api_module._invalidate_analysis_settings_cache(session, "stock")
        api_module.screen_db_stocks(
            "default", limit=50, offset=0, access=_access(), db=session,
        )
        assert calls["screen"] == 3
    finally:
        api_module._SCREENER_RESPONSE_CACHE.invalidate()


def test_system_screener_cache_key_changes_with_preset_revision():
    session = _FakeSession()
    access = _access()
    base = {
        "active_variant": "owner",
        "revision": 8,
        "factory_version": "1",
    }
    first = api_module._system_screener_cache_key(
        session,
        asset_type="stock",
        strategy_id="default",
        limit=50,
        offset=0,
        setting=base,
        access=access,
    )
    second = api_module._system_screener_cache_key(
        session,
        asset_type="stock",
        strategy_id="default",
        limit=50,
        offset=0,
        setting={**base, "revision": 9},
        access=access,
    )
    assert first != second
