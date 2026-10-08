"""Measure time-to-usable for the official staging journeys in a real browser.

This operator-only tool is intentionally outside the production image.  Export a
logged-in Playwright storage state once and reuse it while it remains valid.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter


async def wait_usable(page, root: str) -> None:
    await page.wait_for_selector(root, state="visible", timeout=30_000)
    await page.wait_for_function(
        """selector => {
          const root=document.querySelector(selector);
          return Boolean(root && !root.classList.contains('panel-refreshing') &&
            !root.querySelector('.skeleton,.loading-grid') && root.childElementCount);
        }""",
        arg=root,
        timeout=30_000,
    )


async def measure(action, page, root: str) -> float:
    started = perf_counter()
    await action()
    await wait_usable(page, root)
    return round((perf_counter() - started) * 1000, 2)


async def run(args) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - operator guidance
        raise SystemExit(
            "Instale requirements-browser.txt e execute 'playwright install chromium'."
        ) from exc

    state_path = Path(args.storage_state).resolve() if args.storage_state else None
    if state_path and not state_path.is_file():
        raise SystemExit(f"Sessão do navegador não encontrada: {state_path}")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.show_browser)
        context = await browser.new_context(
            storage_state=str(state_path) if state_path else None,
            viewport={"width": 1440, "height": 960},
        )
        page = await context.new_page()
        results: dict[str, list[float]] = {}

        for _ in range(args.samples):
            await page.goto("about:blank")
            entry_started = perf_counter()
            await page.goto(args.base_url, wait_until="domcontentloaded", timeout=45_000)
            if await page.locator("#login-view:not(.hidden)").count():
                raise SystemExit(
                    "A sessão não está autenticada. Gere novamente o arquivo --storage-state."
                )
            await wait_usable(page, "#view-dashboard.active #dashboard-tab-content")
            results.setdefault("platform_entry", []).append(round((perf_counter()-entry_started)*1000,2))
            results.setdefault("analysis_first_open", []).append(
                await measure(
                    lambda: page.click('.nav-item[data-view="analysis"]'),
                    page,
                    "#view-analysis.active #analysis-table",
                )
            )
            results.setdefault("asset_detail", []).append(
                await measure(
                    lambda: page.click('#analysis-table tr[data-ticker]:first-child'),
                    page,
                    "#asset-dialog[open] #asset-dialog-content",
                )
            )
            await page.click("#close-asset-dialog")
            results.setdefault("portfolio", []).append(
                await measure(
                    lambda: page.click('.nav-item[data-view="portfolio"]'),
                    page,
                    "#view-portfolio.active #portfolio-tab-content",
                )
            )
            results.setdefault("backtests", []).append(
                await measure(
                    lambda: page.click('.nav-item[data-view="backtests"]'),
                    page,
                    "#view-backtests.active #backtests-tab-content",
                )
            )
            results.setdefault("analysis_return", []).append(
                await measure(
                    lambda: page.click('.nav-item[data-view="analysis"]'),
                    page,
                    "#view-analysis.active #analysis-table",
                )
            )

        await browser.close()

    summary = {
        name: {
            "samples": values,
            "p50_ms": round(median(values), 2),
            "max_ms": round(max(values), 2),
            "target_ms": args.target_ms,
            "within_target": median(values) <= args.target_ms,
        }
        for name, values in results.items()
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "browser": "chromium",
        "summary": summary,
        "passed": all(item["within_target"] for item in summary.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Homologa a experiência real no navegador.")
    parser.add_argument(
        "--base-url",
        default="https://formacaodoinvestidor.com.br/testefdi/plataforma/",
    )
    parser.add_argument("--storage-state", help="Arquivo Playwright de uma sessão de teste autenticada.")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--target-ms", type=float, default=4_000)
    parser.add_argument("--output", default="browser-performance-report.json")
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.samples <= 20:
        parser.error("--samples deve ficar entre 1 e 20")
    report = asyncio.run(run(args))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
