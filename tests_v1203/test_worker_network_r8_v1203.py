from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_worker_has_external_and_database_networks():
    compose = (ROOT / "docker-compose.oracle-web.yml").read_text(encoding="utf-8")
    worker = re.search(r"(?ms)^  worker:\n(?P<body>.*?)(?=^  proxy:)", compose)
    assert worker is not None
    networks = re.search(r"(?ms)^    networks:\n(?P<body>.*?)(?=^    [a-z_]+:)", worker.group("body"))
    assert networks is not None
    network_body = networks.group("body")
    assert network_body.index("- frontend") < network_body.index("- backend")
    assert re.search(r"(?ms)^  backend:\n    internal: true", compose)


def test_windows_publication_preserves_shell_script_execution():
    publication = (ROOT / "PUBLICAR_GITHUB.ps1").read_text(encoding="utf-8")
    assert 'Get-ChildItem -LiteralPath $publicationRoot -File -Filter "*.sh" -Recurse' in publication
    assert "update-index --chmod=+x" in publication
    assert "Path.GetRelativePath" in publication
    assert ".Substring($publicationRoot.Length)" in publication
    assert "V1.20.3 R8" in publication
