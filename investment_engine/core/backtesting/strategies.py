from __future__ import annotations

from dataclasses import dataclass, asdict
import pandas as pd


@dataclass(frozen=True)
class StrategyDefinition:
    id: str
    name: str
    family: str
    description: str
    rules: str
    default_params: dict
    parameter_schema: dict
    warmup_bars: int

    def as_dict(self):
        return asdict(self)


STRATEGIES = {
    "ema9_sma50": StrategyDefinition(
        id="ema9_sma50", name="EMA 9 × SMA 50", family="Tendência / crossover",
        description="Mantém posição comprada quando a média exponencial de 9 períodos está acima da média simples de 50.",
        rules="Entrada no próximo pregão após EMA9 > SMA50; saída no próximo pregão após EMA9 <= SMA50.",
        default_params={"fast_period": 9, "slow_period": 50}, parameter_schema={}, warmup_bars=60,
    ),
    "ema9_sma40": StrategyDefinition(
        id="ema9_sma40", name="EMA 9 × SMA 40", family="Tendência / crossover",
        description="Versão um pouco mais rápida do crossover solicitado, usando EMA9 contra SMA40.",
        rules="Entrada no próximo pregão após EMA9 > SMA40; saída no próximo pregão após EMA9 <= SMA40.",
        default_params={"fast_period": 9, "slow_period": 40}, parameter_schema={}, warmup_bars=50,
    ),
    "sma3_ema9_sma21": StrategyDefinition(
        id="sma3_ema9_sma21", name="SMA 3 + EMA 9 + SMA 21", family="Tendência / alinhamento",
        description="Busca alinhamento de curto prazo: média de 3 acima da EMA9 e EMA9 acima da SMA21.",
        rules="Comprado enquanto SMA3 > EMA9 > SMA21; fora do mercado quando o alinhamento é perdido.",
        default_params={"fast_period": 3, "mid_period": 9, "slow_period": 21}, parameter_schema={}, warmup_bars=30,
    ),
    "sma50_sma200": StrategyDefinition(
        id="sma50_sma200", name="Golden Cross SMA 50 × SMA 200", family="Tendência / crossover",
        description="Filtro clássico de tendência intermediária versus tendência longa.",
        rules="Comprado quando SMA50 > SMA200; fora quando SMA50 <= SMA200.",
        default_params={"fast_period": 50, "slow_period": 200}, parameter_schema={}, warmup_bars=220,
    ),
    "macd_12_26_9": StrategyDefinition(
        id="macd_12_26_9", name="MACD 12/26/9", family="Momentum / tendência",
        description="Usa a relação entre MACD e sua linha de sinal para acompanhar mudanças de momentum.",
        rules="Comprado quando MACD > linha de sinal; fora quando MACD <= linha de sinal.",
        default_params={"fast": 12, "slow": 26, "signal": 9}, parameter_schema={}, warmup_bars=45,
    ),
    "rsi14_sma200": StrategyDefinition(
        id="rsi14_sma200", name="RSI 14 reversão + filtro SMA 200", family="Reversão à média",
        description="Procura sobrevenda apenas quando o ativo ainda está acima da tendência longa, reduzindo entradas contra quedas estruturais.",
        rules="Entrada quando RSI14 < 30 e preço > SMA200; saída quando RSI14 > 55 ou preço < SMA200.",
        default_params={"rsi_period": 14, "entry_rsi": 30, "exit_rsi": 55, "trend_period": 200}, parameter_schema={}, warmup_bars=220,
    ),
    "donchian_20_10": StrategyDefinition(
        id="donchian_20_10", name="Donchian Breakout 20/10", family="Trend following / breakout",
        description="Sistema de rompimento: entra em nova máxima e sai em perda do canal mais curto.",
        rules="Entrada acima da máxima dos 20 pregões anteriores; saída abaixo da mínima dos 10 pregões anteriores.",
        default_params={"entry_period": 20, "exit_period": 10}, parameter_schema={}, warmup_bars=30,
    ),
    "bollinger_rsi_trend": StrategyDefinition(
        id="bollinger_rsi_trend", name="Bollinger 20/2 + RSI + SMA 200", family="Reversão à média",
        description="Combina extremo de preço, momentum e filtro de tendência. Os parâmetros são configuráveis para testar sensibilidade sem esconder a regra usada.",
        rules="Entrada quando o gatilho configurado da banda inferior, o limite do RSI e o filtro estrutural selecionado ocorrem juntos; saída na média central, no limite de RSI ou na falha do filtro estrutural. Consulte o mapa do teste para ver a regra efetivamente executada.",
        default_params={"period": 20, "stddev": 2.0, "rsi_period": 14, "entry_rsi": 35, "exit_rsi": 55, "trend_period": 200, "trend_filter_mode": "price_above", "trend_slope_lookback": 20, "band_trigger": "close"},
        parameter_schema={
            "period": {"type": "int", "min": 10, "max": 100},
            "stddev": {"type": "float", "min": 1.0, "max": 4.0},
            "rsi_period": {"type": "int", "min": 2, "max": 50},
            "entry_rsi": {"type": "float", "min": 10, "max": 60},
            "exit_rsi": {"type": "float", "min": 40, "max": 90},
            "trend_period": {"type": "int", "min": 20, "max": 400},
            "trend_filter_mode": {"type": "choice", "options": ["price_above", "sma_rising", "price_above_and_sma_rising", "price_above_or_sma_rising", "none"]},
            "trend_slope_lookback": {"type": "int", "min": 1, "max": 100},
            "band_trigger": {"type": "choice", "options": ["close", "low_touch", "close_reentry"]},
        }, warmup_bars=220,
    ),
    "momentum_12m": StrategyDefinition(
        id="momentum_12m", name="Momentum de 12 meses", family="Trend following / momentum",
        description="Compara o preço ajustado atual com o de aproximadamente 12 meses atrás para capturar persistência de tendência de prazo mais longo.",
        rules="Comprado quando o preço está acima do preço de 252 pregões atrás; fora quando fica abaixo.",
        default_params={"lookback": 252}, parameter_schema={}, warmup_bars=280,
    ),
    "custom_ma_cross": StrategyDefinition(
        id="custom_ma_cross", name="Cruzamento de médias personalizado", family="Tendência / crossover",
        description="Permite testar outras combinações sem alterar o código.",
        rules="Comprado quando a média rápida está acima da média lenta; execução no pregão seguinte ao sinal.",
        default_params={"fast_period": 9, "slow_period": 40, "fast_type": "ema", "slow_type": "sma"},
        parameter_schema={
            "fast_period": {"type": "int", "min": 2, "max": 200},
            "slow_period": {"type": "int", "min": 3, "max": 400},
            "fast_type": {"type": "choice", "options": ["sma", "ema"]},
            "slow_type": {"type": "choice", "options": ["sma", "ema"]},
        },
        warmup_bars=420,
    ),
}


def strategy_catalog() -> list[dict]:
    return [s.as_dict() for s in STRATEGIES.values()]


def _ma(price: pd.Series, period: int, kind: str) -> pd.Series:
    if kind.lower() == "ema":
        return price.ewm(span=period, adjust=False, min_periods=period).mean()
    return price.rolling(period, min_periods=period).mean()


def _rsi(price: pd.Series, period: int = 14) -> pd.Series:
    delta = price.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.mask(lambda x: x == 0)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100.0).where(avg_gain.notna())


def _stateful_entry_exit(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    state = 0
    out = []
    for ent, ext in zip(entry.fillna(False), exit_.fillna(False)):
        if state == 0 and bool(ent):
            state = 1
        elif state == 1 and bool(ext):
            state = 0
        out.append(state)
    return pd.Series(out, index=entry.index, dtype=float)


def build_signal(df: pd.DataFrame, strategy_id: str, params: dict | None = None) -> tuple[pd.Series, pd.DataFrame, dict]:
    if strategy_id not in STRATEGIES:
        raise ValueError("strategy_not_found")
    definition = STRATEGIES[strategy_id]
    p = {**definition.default_params, **(params or {})}
    x = df.copy()
    price = x["price"].astype(float)
    indicators = pd.DataFrame(index=x.index)

    if strategy_id in {"ema9_sma50", "ema9_sma40"}:
        fast = _ma(price, int(p["fast_period"]), "ema")
        slow = _ma(price, int(p["slow_period"]), "sma")
        indicators["EMA rápida"] = fast; indicators["SMA lenta"] = slow
        signal = (fast > slow).where(fast.notna() & slow.notna())

    elif strategy_id == "sma3_ema9_sma21":
        fast = _ma(price, int(p["fast_period"]), "sma")
        mid = _ma(price, int(p["mid_period"]), "ema")
        slow = _ma(price, int(p["slow_period"]), "sma")
        indicators["SMA 3"] = fast; indicators["EMA 9"] = mid; indicators["SMA 21"] = slow
        signal = ((fast > mid) & (mid > slow)).where(fast.notna() & mid.notna() & slow.notna())

    elif strategy_id == "sma50_sma200":
        fast = _ma(price, int(p["fast_period"]), "sma")
        slow = _ma(price, int(p["slow_period"]), "sma")
        indicators["SMA 50"] = fast; indicators["SMA 200"] = slow
        signal = (fast > slow).where(fast.notna() & slow.notna())

    elif strategy_id == "macd_12_26_9":
        ema_fast = _ma(price, int(p["fast"]), "ema")
        ema_slow = _ma(price, int(p["slow"]), "ema")
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=int(p["signal"]), adjust=False, min_periods=int(p["signal"])).mean()
        indicators["MACD"] = macd; indicators["Sinal MACD"] = macd_signal
        signal = (macd > macd_signal).where(macd.notna() & macd_signal.notna())

    elif strategy_id == "rsi14_sma200":
        rsi = _rsi(price, int(p["rsi_period"]))
        trend = _ma(price, int(p["trend_period"]), "sma")
        indicators["RSI"] = rsi; indicators["SMA 200"] = trend
        valid = rsi.notna() & trend.notna()
        entry = valid & (rsi < float(p["entry_rsi"])) & (price > trend)
        exit_ = valid & ((rsi > float(p["exit_rsi"])) | (price < trend))
        signal = _stateful_entry_exit(entry, exit_).where(valid)

    elif strategy_id == "donchian_20_10":
        ep, xp = int(p["entry_period"]), int(p["exit_period"])
        upper = price.rolling(ep, min_periods=ep).max().shift(1)
        lower = price.rolling(xp, min_periods=xp).min().shift(1)
        indicators[f"Donchian {ep} máx."] = upper; indicators[f"Donchian {xp} mín."] = lower
        valid = upper.notna() & lower.notna()
        signal = _stateful_entry_exit(valid & (price > upper), valid & (price < lower)).where(valid)

    elif strategy_id == "bollinger_rsi_trend":
        period = int(p["period"]); stddev = float(p["stddev"])
        mid = price.rolling(period, min_periods=period).mean()
        sd = price.rolling(period, min_periods=period).std(ddof=0)
        lower = mid - stddev * sd
        upper = mid + stddev * sd
        rsi_period = int(p.get("rsi_period", 14))
        rsi = _rsi(price, rsi_period)
        trend_period = int(p["trend_period"])
        trend = _ma(price, trend_period, "sma")
        slope_lookback = int(p.get("trend_slope_lookback", 20))
        trend_prev = trend.shift(slope_lookback)
        trend_rising = trend > trend_prev
        trend_mode = str(p.get("trend_filter_mode", "price_above"))
        if trend_mode == "price_above":
            trend_ok = price > trend
            trend_exit = price < trend
            trend_valid = trend.notna()
        elif trend_mode == "sma_rising":
            trend_ok = trend_rising
            trend_exit = trend < trend_prev
            trend_valid = trend.notna() & trend_prev.notna()
        elif trend_mode == "price_above_and_sma_rising":
            trend_ok = (price > trend) & trend_rising
            trend_exit = (price < trend) | (trend < trend_prev)
            trend_valid = trend.notna() & trend_prev.notna()
        elif trend_mode == "price_above_or_sma_rising":
            trend_ok = (price > trend) | trend_rising
            trend_exit = (price < trend) & (trend < trend_prev)
            trend_valid = trend.notna() & trend_prev.notna()
        elif trend_mode == "none":
            trend_ok = pd.Series(True, index=x.index, dtype=bool)
            trend_exit = pd.Series(False, index=x.index, dtype=bool)
            trend_valid = pd.Series(True, index=x.index, dtype=bool)
        else:
            raise ValueError("invalid_bollinger_trend_filter_mode")
        indicators["Bollinger média"] = mid; indicators["Bollinger inferior"] = lower; indicators["Bollinger superior"] = upper
        indicators[f"RSI {rsi_period}"] = rsi; indicators["RSI"] = rsi; indicators[f"SMA {trend_period}"] = trend
        indicators[f"SMA {trend_period} ascendente"] = trend_rising.astype(float).where(trend_valid)
        valid = lower.notna() & rsi.notna() & trend_valid
        trigger = str(p.get("band_trigger", "close"))
        if trigger == "low_touch":
            low = pd.to_numeric(x.get("adj_low", x.get("low", price)), errors="coerce")
            band_event = low <= lower
        elif trigger == "close_reentry":
            band_event = (price.shift(1) <= lower.shift(1)) & (price > lower)
        else:
            band_event = price <= lower
        indicators["Gatilho banda inferior"] = band_event.astype(float).where(lower.notna())
        indicators["Filtro estrutural Bollinger"] = trend_ok.astype(float).where(trend_valid)
        entry = valid & band_event & (rsi <= float(p["entry_rsi"])) & trend_ok
        exit_ = valid & ((price >= mid) | (rsi >= float(p["exit_rsi"])) | trend_exit)
        signal = _stateful_entry_exit(entry, exit_).where(valid)

    elif strategy_id == "momentum_12m":
        lookback = int(p["lookback"])
        reference = price.shift(lookback)
        indicators[f"Preço {lookback} pregões atrás"] = reference
        signal = (price > reference).where(reference.notna())

    elif strategy_id == "custom_ma_cross":
        fp, sp = int(p["fast_period"]), int(p["slow_period"])
        if fp >= sp:
            raise ValueError("fast_period_must_be_lower_than_slow_period")
        fast = _ma(price, fp, str(p["fast_type"]))
        slow = _ma(price, sp, str(p["slow_type"]))
        indicators[f"{str(p['fast_type']).upper()} {fp}"] = fast
        indicators[f"{str(p['slow_type']).upper()} {sp}"] = slow
        signal = (fast > slow).where(fast.notna() & slow.notna())

    else:
        raise ValueError("strategy_not_implemented")

    return signal.astype(float), indicators, p


def warmup_bars(strategy_id: str, params: dict | None = None) -> int:
    if strategy_id not in STRATEGIES:
        raise ValueError("strategy_not_found")
    if strategy_id == "custom_ma_cross":
        p = {**STRATEGIES[strategy_id].default_params, **(params or {})}
        return max(int(p["fast_period"]), int(p["slow_period"])) + 20
    return STRATEGIES[strategy_id].warmup_bars
