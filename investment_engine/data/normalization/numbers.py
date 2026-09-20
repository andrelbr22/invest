from __future__ import annotations

import math
from typing import Any

MISSING_TOKENS = {"", "-", "nan", "n/a", "n/d", "none", "null", "--"}


def parse_br_number(value: Any) -> float | None:
    """Parse numbers formatted like '1.234,56%' without conflating missing with zero."""
    if value is None:
        return None
    if hasattr(value, "get_text"):
        value = value.get_text(strip=True)
    text = str(value).strip()
    if text.lower() in MISSING_TOKENS:
        return None
    text = text.replace("%", "").replace("R$", "").strip()
    text = text.replace(".", "").replace(",", ".")
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
