from __future__ import annotations
from .valuation.graham import implied_book_value_per_share, implied_eps, graham_number, add_upside
from .valuation.dividend_target import implied_dividend_per_share, dividend_yield_target_price
from .valuation.technical import distance_pct


def enrich_stock(row: dict) -> dict:
    out = dict(row)
    price = out.get("price")
    bvps = implied_book_value_per_share(price, out.get("pbv"))
    eps = implied_eps(price, out.get("pe"))
    g = add_upside(graham_number(eps, bvps), price)
    dps = implied_dividend_per_share(price, out.get("dividend_yield_pct"))
    d = dividend_yield_target_price(dps, 6.0)
    d = add_upside(d, price)
    out.update({
        "bvps_implied": bvps,
        "eps_implied": eps,
        "graham_number": g.value,
        "graham_upside_pct": g.upside_pct,
        "dividend_target_price": d.value,
        "dividend_target_upside_pct": d.upside_pct,
        "distance_sma200_pct": distance_pct(price, out.get("sma200")),
    })
    return out


def enrich_fii(row: dict) -> dict:
    out = dict(row)
    price = out.get("price")
    dps = implied_dividend_per_share(price, out.get("dividend_yield_pct"))
    d = add_upside(dividend_yield_target_price(dps, 6.0), price)
    out.update({
        "dividend_target_price": d.value,
        "dividend_target_upside_pct": d.upside_pct,
        "distance_sma200_pct": distance_pct(price, out.get("sma200")),
    })
    return out
