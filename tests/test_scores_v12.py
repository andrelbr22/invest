from investment_engine.core.scoring.fundamental import quality_score,value_score,growth_score
from investment_engine.core.quality.data_quality import data_quality

def test_high_quality_scores_high():
    x=quality_score({"roe_pct":25,"roic_pct":22,"ebit_margin_pct":25,"net_margin_pct":18,"net_debt_to_ebitda":0.5,"current_ratio":2})
    assert x.score>90 and x.coverage==100
def test_missing_reduces_coverage_not_score_to_zero():
    x=growth_score({"revenue_cagr_5y_pct":12,"earnings_cagr_5y_pct":None}); assert x.score is not None and x.coverage<100
def test_data_quality_missing():
    q=data_quality({"a":1,"b":None},["a","b"]); assert q.completeness==50
