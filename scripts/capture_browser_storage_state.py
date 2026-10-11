"""Create a local Playwright session file after an interactive owner login."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Abre o staging para login manual e salva a sessão sem exibir seus cookies."
    )
    parser.add_argument(
        "--url", default="https://formacaodoinvestidor.com.br/testefdi/plataforma/"
    )
    parser.add_argument("--output", default="storage-state-staging-owner.json")
    args = parser.parse_args()
    if "/testefdi/" not in args.url:
        raise SystemExit("A sessão de homologação deve ser criada somente em /testefdi/.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Instale requirements-browser.txt e execute 'playwright install chromium'."
        ) from exc

    target = Path(args.output).expanduser().resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=45_000)
        print("Conclua o login do proprietário no navegador aberto.")
        input("Quando o painel principal estiver visível, pressione ENTER aqui: ")
        if page.locator("#login-view:not(.hidden)").count():
            browser.close()
            raise SystemExit("O painel ainda mostra a tela de login; a sessão não foi salva.")
        temporary = target.with_name(f".{target.name}.tmp")
        context.storage_state(path=str(temporary))
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        browser.close()
    print(f"Sessão salva em {target}. Trate o arquivo como senha e nunca publique no Git.")


if __name__ == "__main__":
    main()

