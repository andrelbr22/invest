from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operational_files_use_only_the_oracle_canonical_domain():
    operational_files = [
        ROOT / ".streamlit" / "secrets.toml.example",
        ROOT / "deployment" / "secrets" / "streamlit_secrets.toml.example",
        ROOT / "deployment" / "site" / "index.html",
        ROOT / "streamlit_app.py",
        ROOT / "investment_engine" / "cloud_runtime.py",
        ROOT / "DEPLOY_STREAMLIT_CLOUD.md",
        ROOT / "PRODUCAO_V160.md",
    ]
    forbidden = [
        ".".join(("streamlit", "app")),
        "Streamlit " + "Community Cloud",
        "app" + ".formacaodoinvestidor.com.br",
        "invest" + "-klpbhuewpmzb7njdsmha4t",
    ]
    for path in operational_files:
        contents = path.read_text(encoding="utf-8")
        assert "https://formacaodoinvestidor.com.br" in contents or path.name in {
            "streamlit_app.py", "cloud_runtime.py"
        }
        for legacy_reference in forbidden:
            assert legacy_reference not in contents


def test_runtime_identifies_the_self_hosted_oracle_environment():
    entrypoint = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("APP_ENVIRONMENT", "oracle-production")' in entrypoint
    assert 'os.environ["EXPECTED_EMBEDDED_API_VERSION"] = "0.13.3"' in entrypoint


def test_publication_refuses_an_accidental_nested_project_copy():
    script = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert "$nestedProjectIndicators" in script
    assert "copia completa do projeto dentro da pasta investment_engine" in script
