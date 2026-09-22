from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_owner_only_admin_tab_exposes_filters_and_columns():
    html = (ROOT / "investment_engine/web/index.html").read_text(encoding="utf-8")
    source = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")

    assert 'class="tab owner-only hidden" data-tab="analysis-settings"' in html
    assert "async function loadAdminAnalysisSettings" in source
    assert 'api("/admin/analysis-settings"' in source
    assert 'state.tabs.admin==="analysis-settings"' in source


def test_admin_can_save_enable_and_reset_presets_without_overwriting_factory():
    source = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")

    assert "Padrão original preservado" in source
    assert "Esta referência é imutável" in source
    assert "Salvar configuração alternativa" in source
    assert "/admin/analysis-settings/presets/" in source
    assert "/reset`" in source
    assert "expected_revision" in source
    assert "owner_enabled" in source


def test_admin_column_order_and_user_default_reset_are_available():
    source = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "investment_engine/web/static/app.css").read_text(encoding="utf-8")

    assert "function orderedAnalysisColumns" in source
    assert "data-move-admin-column" in source
    assert "Salvar colunas e ordem" in source
    assert "Restaurar colunas originais" in source
    assert "data-reset-personal-columns" in source
    assert ".admin-column-order" in css


def test_active_owner_preset_uses_validated_advanced_screen_endpoint():
    source = (ROOT / "investment_engine/web/static/app.js").read_text(encoding="utf-8")

    assert 'presetItem?.active_variant==="owner"' in source
    assert 'api("/screen/advanced"' in source
    assert "configuração administrativa ativa" in source
