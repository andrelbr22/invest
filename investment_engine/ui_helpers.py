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


def merge_purchase_position(existing_quantity, existing_average_price, purchase_quantity, purchase_price) -> tuple[float, float]:
    """Return consolidated quantity and weighted average for a new purchase."""
    old_quantity=float(existing_quantity or 0)
    bought_quantity=float(purchase_quantity or 0)
    bought_price=float(purchase_price or 0)
    if old_quantity < 0 or bought_quantity <= 0 or bought_price <= 0:
        raise ValueError("Quantidade e preço da compra devem ser maiores que zero.")
    new_quantity=old_quantity+bought_quantity
    if old_quantity>0 and existing_average_price is not None:
        new_average=((old_quantity*float(existing_average_price))+(bought_quantity*bought_price))/new_quantity
    else:
        new_average=bought_price
    return new_quantity,new_average
