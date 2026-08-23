from __future__ import annotations


def format_brl_price_input(value) -> str:
    """Format a price for a Brazilian text field with exactly two decimals."""
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return f"{number:.2f}".replace(".", ",")


def parse_brl_price_input(value: str | None) -> float | None:
    """Accept 12,34 or 12.34 and return None for an intentionally blank field."""
    clean = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not clean:
        return None
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    elif "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    try:
        number = float(clean)
    except ValueError as exc:
        raise ValueError("Informe o preço no formato 12,34.") from exc
    if number < 0:
        raise ValueError("O preço não pode ser negativo.")
    return round(number, 2)
