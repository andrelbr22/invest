"""Measure official staging journeys from click to usable content in Chromium.

The report complements the API benchmark with download, JavaScript, layout and
paint time. It is an operator-only tool and never changes application data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter


REQUIRED_JOURNEYS = (
    "platform_entry",
    "analysis_first_open",
    "asset_detail",
    "portfolio",
    "finances",
    "backtests",
    "admin",
    "analysis_return",
    "dashboard_return",
)
WARM_JOURNEYS = {"analysis_return", "dashboard_return"}


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile_value) - 1)
    return ordered[index]


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

    state_path = Path(args.storage_state).resolve()
    if not state_path.is_file():
        raise SystemExit(f"Sessão do navegador não encontrada: {state_path}")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.show_browser)
        context = None
        results: dict[str, list[float]] = {}

        for _ in range(args.samples):
            if context:
                await context.close()
            context = await browser.new_context(
                storage_state=str(state_path), viewport={"width": 1440, "height": 960}
            )
            page = await context.new_page()

            async def click_journey(name: str, selector: str, root: str) -> None:
                if not await page.locator(selector).count():
                    return
                results.setdefault(name, []).append(
                    await measure(lambda: page.click(selector), page, root)
                )

            entry_started = perf_counter()
            await page.goto(args.base_url, wait_until="domcontentloaded", timeout=45_000)
            if await page.locator("#login-view:not(.hidden)").count():
                raise SystemExit(
                    "A sessão não está autenticada. Gere novamente o arquivo --storage-state."
                )
            await wait_usable(page, "#view-dashboard.active #dashboard-tab-content")
            results.setdefault("platform_entry", []).append(
                round((perf_counter() - entry_started) * 1000, 2)
            )
            await click_journey(
                "analysis_first_open", '.nav-item[data-view="analysis"]',
                "#view-analysis.active #analysis-table",
            )
            await click_journey(
                "asset_detail", "#analysis-table tr[data-ticker]:first-child",
                "#asset-dialog[open] #asset-dialog-content",
            )
            if await page.locator("#asset-dialog[open]").count():
                await page.click("#close-asset-dialog")
            await click_journey(
                "portfolio", '.nav-item[data-view="portfolio"]',
                "#view-portfolio.active #portfolio-tab-content",
            )
            await click_journey(
                "finances", '.nav-item[data-view="finances"]',
                "#view-finances.active #finances-tab-content",
            )
            await click_journey(
                "backtests", '.nav-item[data-view="backtests"]',
                "#view-backtests.active #backtests-tab-content",
            )
            await click_journey(
                "admin", '.nav-item[data-view="admin"]',
                "#view-admin.active #admin-tab-content",
            )
            await click_journey(
                "analysis_return", '.nav-item[data-view="analysis"]',
                "#view-analysis.active #analysis-table",
            )
            await click_journey(
                "dashboard_return", '.nav-item[data-view="dashboard"]',
                "#view-dashboard.active #dashboard-tab-content",
            )

        if context:
            await context.close()
        await browser.close()

    missing = [name for name in REQUIRED_JOURNEYS if len(results.get(name, [])) < args.samples]
    summary = {}
    for name, values in results.items():
        target = args.warm_target_ms if name in WARM_JOURNEYS else args.cold_target_ms
        p95 = round(percentile(values, 0.95), 2)
        summary[name] = {
            "samples": values,
            "sample_count": len(values),
            "p50_ms": round(median(values), 2),
            "p95_ms": p95,
            "max_ms": round(max(values), 2),
            "target_ms": target,
            "within_target": p95 <= target,
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_commit": args.commit or os.getenv("FDI_RELEASE_COMMIT") or "unknown",
        "base_url": args.base_url,
        "browser": "chromium",
        "required_journeys": list(REQUIRED_JOURNEYS),
        "missing_journeys": missing,
        "summary": summary,
        "passed": not missing and all(item["within_target"] for item in summary.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Homologa a experiência real no navegador.")
    parser.add_argument(
        "--base-url", default="https://formacaodoinvestidor.com.br/testefdi/plataforma/"
    )
    parser.add_argument(
        "--storage-state", required=True,
        help="Arquivo Playwright com uma sessão autenticada do proprietário.",
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--cold-target-ms", type=float, default=4_000)
    parser.add_argument("--warm-target-ms", type=float, default=1_000)
    parser.add_argument("--commit", help="Commit homologado no staging.")
    parser.add_argument("--output", default="browser-performance-report.json")
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()
    if not 3 <= args.samples <= 20:
        parser.error("--samples deve ficar entre 3 e 20")
    report = asyncio.run(run(args))
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
