from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from investment_engine.core.portfolio.service import build_portfolio_snapshot
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.repositories.portfolio import PortfolioRepository
from investment_engine.infrastructure.db.base import Base


def test_portfolio_weights_include_cash_and_within_class():
    snap = build_portfolio_snapshot([
        {"ticker":"AAA3","asset_type":"stock","sector":"Finance","stage":"position","quantity":10,"average_price":80,"current_price":100,"target_weight_pct":40},
        {"ticker":"BBB3","asset_type":"stock","sector":"Utilities","stage":"position","quantity":5,"average_price":90,"current_price":100,"target_weight_pct":20},
        {"ticker":"FII11","asset_type":"fii","segment":"Logística","stage":"position","quantity":5,"average_price":90,"current_price":100,"target_weight_pct":20},
    ], cash_balance=500, target_cash_pct=20)
    assert snap["summary"]["market_value"] == 2500
    assert snap["summary"]["target_is_balanced"] is True
    aaa = next(x for x in snap["positions"] if x["ticker"] == "AAA3")
    assert round(aaa["current_weight_pct"], 2) == 40.0
    assert round(aaa["within_class_current_pct"], 2) == 66.67
    cash = next(x for x in snap["class_allocation"] if x["asset_class"] == "cash")
    assert round(cash["current_weight_pct"], 2) == 20.0


def test_target_and_analysis_do_not_inflate_current_value():
    snap = build_portfolio_snapshot([
        {"ticker":"AAA3","asset_type":"stock","stage":"position","quantity":10,"current_price":10,"target_weight_pct":50},
        {"ticker":"NEW3","asset_type":"stock","stage":"target","quantity":100,"current_price":20,"target_weight_pct":30},
        {"ticker":"IDEA3","asset_type":"stock","stage":"analysis","quantity":100,"current_price":30,"target_weight_pct":0},
    ], cash_balance=100, target_cash_pct=20)
    assert snap["summary"]["market_value"] == 200
    new = next(x for x in snap["positions"] if x["ticker"] == "NEW3")
    assert new["market_value"] == 0
    assert new["target_value"] == 60


def test_portfolio_repository_upserts_same_asset():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ar = AssetRepository(session); pr = PortfolioRepository(session)
        a = ar.upsert_asset(ticker="ABCD3", asset_type="stock")
        p = pr.create_portfolio(name="Principal")
        x = pr.upsert_position(p, a, quantity=10, average_price=10, target_weight_pct=20)
        y = pr.upsert_position(p, a, quantity=20, average_price=11, target_weight_pct=25)
        session.commit()
        assert x.id == y.id
        assert float(y.quantity) == 20
        assert len(pr.positions(p.id)) == 1


def test_missing_quote_is_not_treated_as_zero_or_total_loss():
    snap = build_portfolio_snapshot([
        {"ticker":"AAA3","asset_type":"stock","stage":"position","quantity":10,"average_price":10,"current_price":None,"target_weight_pct":80},
    ], cash_balance=200, target_cash_pct=20)
    pos = snap["positions"][0]
    assert pos["market_value"] is None
    assert pos["pnl_value"] is None
    assert pos["current_weight_pct"] is None
    assert snap["summary"]["market_value"] is None
    assert snap["summary"]["unrealized_pnl"] is None
    assert snap["summary"]["missing_price_positions"] == 1
    assert snap["summary"]["allocation_complete"] is False


def test_analysis_stage_does_not_change_target_allocation_even_if_weight_was_typed():
    snap = build_portfolio_snapshot([
        {"ticker":"AAA3","asset_type":"stock","stage":"position","quantity":10,"current_price":10,"target_weight_pct":60},
        {"ticker":"IDEA3","asset_type":"stock","stage":"analysis","quantity":0,"current_price":20,"target_weight_pct":25},
    ], cash_balance=40, target_cash_pct=40)
    idea = next(x for x in snap["positions"] if x["ticker"] == "IDEA3")
    assert idea["effective_target_weight_pct"] == 0
    assert idea["target_value"] == 0
    assert snap["summary"]["target_total_pct"] == 100
