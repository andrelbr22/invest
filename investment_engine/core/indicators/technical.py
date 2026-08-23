from __future__ import annotations
import math
from statistics import pstdev


def _clean(values): return [float(x) for x in values if x is not None]
def sma(values, period):
    v=_clean(values)
    return None if len(v)<period else sum(v[-period:])/period

def rsi(values, period=14):
    v=_clean(values)
    if len(v)<period+1: return None
    changes=[v[i]-v[i-1] for i in range(len(v)-period,len(v))]
    gains=sum(max(c,0) for c in changes)/period
    losses=sum(max(-c,0) for c in changes)/period
    if losses==0: return 100.0 if gains>0 else 50.0
    rs=gains/losses
    return 100-(100/(1+rs))

def bollinger(values, period=20, deviations=2.0):
    v=_clean(values)
    if len(v)<period: return (None,None,None)
    x=v[-period:]; mid=sum(x)/period; sd=pstdev(x)
    return mid, mid-deviations*sd, mid+deviations*sd

def ema(values, period):
    v=_clean(values)
    if len(v)<period: return None
    k=2/(period+1); e=sum(v[:period])/period
    for x in v[period:]: e=x*k+e*(1-k)
    return e

def macd(values, fast=12, slow=26):
    ef=ema(values,fast); es=ema(values,slow)
    return None if ef is None or es is None else ef-es

def atr(highs,lows,closes,period=14):
    h=_clean(highs); l=_clean(lows); c=_clean(closes)
    n=min(len(h),len(l),len(c))
    if n<period+1: return None
    trs=[]
    for i in range(n-period,n):
        prev=c[i-1]
        trs.append(max(h[i]-l[i],abs(h[i]-prev),abs(l[i]-prev)))
    return sum(trs)/period

def annualized_volatility(values, periods=252):
    v=_clean(values)
    if len(v)<3: return None
    rets=[v[i]/v[i-1]-1 for i in range(1,len(v)) if v[i-1] != 0]
    return pstdev(rets)*math.sqrt(periods)*100 if len(rets)>1 else None

def max_drawdown(values):
    v=_clean(values)
    if not v: return None
    peak=v[0]; worst=0.0
    for x in v:
        peak=max(peak,x)
        if peak: worst=min(worst,x/peak-1)
    return worst*100

def total_return(values, periods):
    v=_clean(values)
    if len(v)<=periods or v[-periods-1]==0: return None
    return (v[-1]/v[-periods-1]-1)*100

def compute_indicators(bars):
    bars=sorted(bars,key=lambda x:x["timestamp"])
    close=[b.get("adjusted_close") if b.get("adjusted_close") is not None else b.get("close") for b in bars]
    high=[b.get("high") for b in bars]; low=[b.get("low") for b in bars]
    mid,bbl,bbu=bollinger(close)
    return {
        "close": close[-1] if close else None, "sma20":sma(close,20), "sma50":sma(close,50), "sma200":sma(close,200),
        "rsi14":rsi(close,14), "bb_middle":mid, "bb_lower":bbl, "bb_upper":bbu,
        "macd":macd(close), "atr14":atr(high,low,close), "volatility_annual_pct":annualized_volatility(close[-253:]),
        "max_drawdown_1y_pct":max_drawdown(close[-253:]), "return_1m_pct":total_return(close,21),
        "return_3m_pct":total_return(close,63), "return_12m_pct":total_return(close,252),
    }
