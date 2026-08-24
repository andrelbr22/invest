# Migration plan — current Streamlit -> Investment Engine V1.1

## Stage A — persist market data

1. Start PostgreSQL and apply Alembic migrations.
2. Run the ingestion script on a schedule.
3. Compare stored snapshots against the current Streamlit output.
4. Do not remove the current scraping path until parity checks are complete.

## Stage B — make Streamlit a client

Replace direct calls to `carregar_dados_acoes()` / `carregar_dados_fiis()` with API reads:

- `GET /assets?asset_type=stock`
- `GET /assets?asset_type=fii`
- `GET /assets/{ticker}`

Keep presentation and filter UI initially, but move filtering/strategies progressively to backend endpoints.

## Stage C — score persistence

Add versioned score snapshots after Quality/Value/Growth/Risk/Technical formulas are finalized. Never backfill a historical score using data that was not known at that date.

## Stage D — Android

Android consumes the same FastAPI. API keys/provider credentials remain server-side. Watchlists, portfolios and alerts can then be added without changing the market-data core.

## Rollout rule

Run old and new paths in parallel until ticker counts, key metrics, missing-data behavior and update timestamps are reconciled. Differences should be observable, not silently coerced to zero.

## V1.5
A migração `0003_v1_5_portfolio_backtests.py` adiciona persistência para carteiras e backtests. Ela também adiciona `classification_override` às posições para classificação manual de ETFs ou casos especiais.

Execute:

```powershell
python -m alembic upgrade head
```
