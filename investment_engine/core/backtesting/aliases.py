from __future__ import annotations

TICKER_ALIASES = {
    "VIVT4": {"ticker": "VIVT3", "reason": "VIVT4 foi convertida em VIVT3 na proporção 1:1 em novembro de 2020"},
    "EMBR3": {"ticker": "EMBJ3", "reason": "o código de negociação da Embraer passou de EMBR3 para EMBJ3 em novembro de 2025"},
}


def resolve_ticker_alias(ticker: str) -> tuple[str, dict | None]:
    requested = ticker.upper().strip()
    alias = TICKER_ALIASES.get(requested)
    return (alias["ticker"], {"requested": requested, **alias}) if alias else (requested, None)
