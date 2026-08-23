from datetime import datetime,timezone,timedelta
from investment_engine.core.indicators.technical import sma,rsi,bollinger,compute_indicators

def test_sma(): assert sma(list(range(1,21)),20)==10.5
def test_rsi_uptrend(): assert rsi(list(range(1,20)))==100.0
def test_compute_has_m200():
    t=datetime.now(timezone.utc); bars=[{"timestamp":t+timedelta(days=i),"open":i+1,"high":i+2,"low":i,"close":i+1,"adjusted_close":i+1} for i in range(260)]
    x=compute_indicators(bars); assert x["sma200"] is not None and x["return_12m_pct"] is not None
