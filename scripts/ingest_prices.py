import argparse

from investment_engine.infrastructure.db.session import get_session_factory
from investment_engine.data.ingestion.prices import PriceIngestionService
from investment_engine.core.repositories.assets import AssetRepository

p = argparse.ArgumentParser(description="Carrega histórico OHLCV para um ou vários ativos.")
p.add_argument("tickers", nargs="*", help="Tickers específicos, ex.: BBAS3 HGLG11 BOVA11")
p.add_argument("--all", action="store_true", help="Carrega todos os ativos ativos do tipo informado.")
p.add_argument("--type", default="stock", choices=["stock", "fii", "etf", "bdr", "other"])
p.add_argument("--range", dest="range_", default="3y", help="Range do Yahoo quando não há datas explícitas. Padrão: 3y")
p.add_argument("--limit", type=int, default=1200, help="Máximo de ativos no modo --all.")
p.add_argument("--offset", type=int, default=0)
args = p.parse_args()

if not args.all and not args.tickers:
    p.error("Informe ao menos um ticker ou use --all.")

Session = get_session_factory()
s = Session()
try:
    repo = AssetRepository(s)
    tickers = [t.upper() for t in args.tickers]
    if args.all:
        tickers = [a.ticker for a in repo.list_assets(asset_type=args.type, limit=args.limit, offset=args.offset)]
    svc = PriceIngestionService(s)
    ok = 0
    failures = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, start=1):
        try:
            result = svc.ingest_asset(ticker, asset_type=args.type, range_=args.range_)
            s.commit()
            ok += 1
            print(f"[{i}/{total}] OK {ticker}: {result.get('bars', 0)} barras")
        except Exception as exc:
            s.rollback()
            failures.append((ticker, str(exc)))
            print(f"[{i}/{total}] ERRO {ticker}: {exc}")
    print(f"Concluído: {ok}/{total} ativo(s) carregados; {len(failures)} falha(s).")
    if failures:
        print("Falhas:")
        for ticker, error in failures[:50]:
            print(f"- {ticker}: {error}")
finally:
    s.close()
