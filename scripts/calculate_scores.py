from investment_engine.infrastructure.db.session import get_session_factory
from investment_engine.infrastructure.config import settings
from investment_engine.core.repositories.assets import AssetRepository
from investment_engine.core.services_v14 import calculate_asset_intelligence
from investment_engine.core.valuation.dividend_target import implied_dividend_per_share, dividend_yield_target_price
from investment_engine.core.valuation.gordon import gordon_growth_value, price_ceiling_with_margin

s=get_session_factory()(); repo=AssetRepository(s)
try:
  processed=0
  for asset_type in ("stock","fii"):
    for a in repo.list_assets(asset_type=asset_type,limit=5000):
      f=repo.latest_fundamentals(a.id)
      if not f: continue
      t=repo.latest_technical(a.id, source="internal") or repo.latest_technical(a.id)
      x=calculate_asset_intelligence(a,f,t)
      if x["graham_number"] is not None:
        repo.upsert_valuation(
          a, method="graham_number", as_of=f.reference_date, method_version="1.4",
          value=x["graham_number"], upside_pct=x["graham_upside_pct"],
          inputs={"price":x["data"].get("price"),"pe":x["data"].get("pe"),"pbv":x["data"].get("pbv")}
        )
      price=x["data"].get("price")
      dy=x["data"].get("dividend_yield_pct")
      dps=implied_dividend_per_share(price,dy)

      # Bazin/Barsi: preço-teto clássico por dividend yield mínimo de 6%.
      barsi=dividend_yield_target_price(dps,target_yield_pct=6.0)
      if barsi.valid and barsi.value is not None:
        barsi_upside=None if not price else (barsi.value/price-1)*100
        repo.upsert_valuation(
          a, method="dividend_yield_target", as_of=f.reference_date, method_version="1.1",
          value=barsi.value, upside_pct=barsi_upside,
          inputs={"price":price,"dividend_yield_pct":dy,"dividend_per_share":dps,"target_yield_pct":6.0,"label":"Preço Teto Bazin/Barsi"}
        )

      # Gordon Growth / DDM: somente ações. Premissas são explícitas e configuráveis no .env.
      if asset_type == "stock" and dps is not None:
        intrinsic=gordon_growth_value(
          dps,
          required_return_pct=settings.gordon_required_return_pct,
          growth_pct=settings.gordon_growth_pct,
        )
        if intrinsic.valid and intrinsic.value is not None:
          ceiling=price_ceiling_with_margin(intrinsic.value,settings.valuation_margin_of_safety_pct)
          if ceiling.valid and ceiling.value is not None:
            ceiling_upside=None if not price else (ceiling.value/price-1)*100
            repo.upsert_valuation(
              a, method="gordon_ddm_ceiling", as_of=f.reference_date, method_version="1.0",
              value=ceiling.value, upside_pct=ceiling_upside,
              inputs={
                "price":price,
                "dividend_per_share_d0":dps,
                "required_return_pct":settings.gordon_required_return_pct,
                "growth_pct":settings.gordon_growth_pct,
                "margin_of_safety_pct":settings.valuation_margin_of_safety_pct,
                "intrinsic_value_before_margin":intrinsic.value,
              }
            )

      scores={
        "quality_score":x["quality"].score,
        "value_score":x["value"].score,
        "growth_score":x["growth"].score if x["growth"] else None,
        "technical_score":x["technical"].score,
        "risk_score":x["risk"].score,
        "liquidity_score":x["liquidity"].score,
        "alb_score":x["alb_score"],
      }
      details={
        "profile":{"key":x["profile"].key,"label":x["profile"].label,"notes":x["profile"].notes,"weights":x["profile"].alb_weights},
        "quality":x["quality"].as_dict(),"value":x["value"].as_dict(),"growth":x["growth"].as_dict() if x["growth"] else None,
        "technical":x["technical"].as_dict(),"risk":x["risk"].as_dict(),"liquidity":x["liquidity"].as_dict(),"explanation":x["explanation"],
      }
      repo.upsert_scores(a,as_of=f.reference_date,model_version=x["model_version"],scores=scores,coverage_pct=x["coverage"],data_quality_score=x["data_quality"].score,details=details)
      processed+=1
  s.commit(); print(f"V1.4.3: {processed} ativos recalculados.")
finally:s.close()
