from pathlib import Path


FRONTEND_MODULES = (
    "feature-portfolio.js",
    "feature-backtests.js",
    "feature-finances.js",
    "feature-admin.js",
    "app.js",
)


def browser_source(root: Path) -> str:
    """Return the complete browser source after the V1.23.7 R2 split."""
    root = Path(root)
    web_root = root if root.name == "web" else root / "investment_engine" / "web"
    static_root = web_root / "static"
    return "\n".join(
        (static_root / module).read_text(encoding="utf-8")
        for module in FRONTEND_MODULES
    )
