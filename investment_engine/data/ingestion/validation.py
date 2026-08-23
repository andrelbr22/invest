from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass
class ValidationResult:
    valid: bool
    quality_score: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_finite(value) -> bool:
    return value is None or (isinstance(value, (int, float)) and math.isfinite(float(value)))


def validate_stock(row: dict) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not row.get("ticker"):
        errors.append("ticker_missing")
    for key, value in row.items():
        if key != "ticker" and isinstance(value, (int, float)) and not _is_finite(value):
            errors.append(f"{key}_non_finite")
    price = row.get("price")
    if price is not None and price <= 0:
        errors.append("price_non_positive")
    for pct_key in ("dividend_yield_pct", "roe_pct", "ebit_margin_pct", "net_margin_pct"):
        value = row.get(pct_key)
        if value is not None and abs(value) > 1000:
            warnings.append(f"{pct_key}_extreme")
    required = ("price", "pe", "pbv", "dividend_yield_pct", "roe_pct", "ebit_margin_pct", "net_margin_pct")
    present = sum(row.get(k) is not None for k in required)
    quality = round(100 * present / len(required), 2)
    return ValidationResult(not errors, quality, errors, warnings)


def validate_fii(row: dict) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not row.get("ticker"):
        errors.append("ticker_missing")
    price = row.get("price")
    if price is not None and price <= 0:
        errors.append("price_non_positive")
    vacancy = row.get("vacancy_pct")
    if vacancy is not None and not (0 <= vacancy <= 100):
        warnings.append("vacancy_out_of_expected_range")
    required = ("price", "pbv", "dividend_yield_pct", "ffo_yield_pct", "cap_rate_pct", "vacancy_pct", "daily_liquidity")
    present = sum(row.get(k) is not None for k in required)
    quality = round(100 * present / len(required), 2)
    return ValidationResult(not errors, quality, errors, warnings)


def validate_technical(row: dict) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not row.get("ticker"):
        errors.append("ticker_missing")
    score = row.get("score_tv")
    if score is not None and not (-1 <= score <= 1):
        warnings.append("score_tv_out_of_expected_range")
    rsi = row.get("rsi14")
    if rsi is not None and not (0 <= rsi <= 100):
        warnings.append("rsi_out_of_range")
    required = ("score_tv", "sma20", "sma50", "sma200", "rsi14", "close")
    present = sum(row.get(k) is not None for k in required)
    quality = round(100 * present / len(required), 2)
    return ValidationResult(not errors, quality, errors, warnings)
