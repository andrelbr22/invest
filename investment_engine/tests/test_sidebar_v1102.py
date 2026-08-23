from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1] / "examples" / "streamlit_v15_integrated.py"
).read_text(encoding="utf-8")


def test_sidebar_has_balanced_navigation_and_identity_cards():
    assert "def _render_sidebar_identity(health):" in SOURCE
    assert 'class="ie-brand"' in SOURCE
    assert 'class="ie-account-card"' in SOURCE
    assert 'class="ie-engine-card"' in SOURCE
    assert 'div[role="radiogroup"] label:has(input:checked)' in SOURCE
    assert "width:100%; min-height:49px" in SOURCE


def test_sidebar_keeps_keyboard_focus_and_removes_redundant_labels():
    assert 'label:has(input:focus-visible)' in SOURCE
    assert "Você está em:" not in SOURCE
    assert "st.sidebar.success" not in SOURCE
    assert 'Perfil: {PERMISSIONS' not in SOURCE
