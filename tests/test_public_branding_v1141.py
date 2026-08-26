from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_ui_has_its_own_icon_and_keeps_only_required_navigation_structure():
    source = (ROOT / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    assert 'page_icon=":material/school:"' in source
    assert 'menu_items={"Get help": None, "Report a Bug": None, "About": None}' in source
    assert '#MainMenu' in source
    assert '[data-testid="stSidebarCollapseButton"]' in source
    assert '[data-testid="stSidebarCollapsedControl"]' in source
    assert '[data-testid="stDecoration"]' in source
    assert 'footer {display:none !important' in source


def test_fixed_sidebar_has_one_exact_content_offset_without_empty_rail():
    source = (ROOT / "examples" / "streamlit_v15_integrated.py").read_text(encoding="utf-8")
    assert 'position:fixed !important; inset:0 auto 0 0 !important' in source
    assert 'padding-left:20rem !important' in source
    assert 'margin-left:0 !important' in source
    assert 'border-right:0 !important' in source
    assert 'width:min(20rem,88vw)' in source


def test_public_toolbar_uses_minimal_mode():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert '[client]' in config
    assert 'toolbarMode = "minimal"' in config


def test_publication_message_references_the_oracle_server():
    script = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert "O servidor Oracle iniciara a atualizacao automaticamente." in script
    assert "O Streamlit iniciara a atualizacao automaticamente." not in script
