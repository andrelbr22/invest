from __future__ import annotations

from dataclasses import dataclass, asdict
import math
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
    requires_benchmark: bool = False

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
    "supertrend_atr": StrategyDefinition(
        id="supertrend_atr", name="Supertrend ATR", family="Tendência / volatilidade",
        description="Acompanha a tendência com uma faixa adaptativa calculada pelo ATR, ficando mais distante quando a volatilidade aumenta.",
        rules="Comprado quando o Supertrend aponta alta; fora quando o fechamento cruza a faixa de baixa. O sinal é executado no pregão seguinte.",
        default_params={"atr_period": 10, "multiplier": 3.0},
        parameter_schema={
            "atr_period": {"type": "int", "min": 5, "max": 50},
            "multiplier": {"type": "float", "min": 1.0, "max": 8.0},
        },
        warmup_bars=60,
    ),
    "dual_momentum_relative": StrategyDefinition(
        id="dual_momentum_relative", name="Momentum dual relativo 12–1", family="Momentum / força relativa",
        description="Exige momentum absoluto positivo no ativo e desempenho superior ao benchmark no mesmo período, desconsiderando o último mês por padrão.",
        rules="Comprado quando o retorno 12–1 do ativo é positivo e supera o benchmark; fora quando uma das duas condições deixa de ser atendida.",
        default_params={
            "lookback": 252, "skip_recent": 21,
            "min_absolute_return_pct": 0.0, "min_excess_return_pct": 0.0,
            "benchmark_ticker": "auto",
        },
        parameter_schema={
            "lookback": {"type": "int", "min": 63, "max": 504},
            "skip_recent": {"type": "int", "min": 0, "max": 63},
            "min_absolute_return_pct": {"type": "float", "min": -50.0, "max": 100.0},
            "min_excess_return_pct": {"type": "float", "min": -50.0, "max": 100.0},
        },
        warmup_bars=290,
        requires_benchmark=True,
    ),
    "bollinger_squeeze_breakout": StrategyDefinition(
        id="bollinger_squeeze_breakout", name="Bollinger Squeeze + rompimento", family="Volatilidade / breakout",
        description="Procura expansão de volatilidade após uma compressão das Bandas de Bollinger, com confirmação opcional de volume.",
        rules="Entrada no rompimento da banda superior depois de um squeeze; saída quando o fechamento perde a média central.",
        default_params={
            "period": 20, "stddev": 2.0, "squeeze_lookback": 120,
            "squeeze_quantile": 0.20, "volume_period": 20, "volume_ratio_min": 1.0,
        },
        parameter_schema={
            "period": {"type": "int", "min": 10, "max": 100},
            "stddev": {"type": "float", "min": 1.0, "max": 4.0},
            "squeeze_lookback": {"type": "int", "min": 40, "max": 504},
            "squeeze_quantile": {"type": "float", "min": 0.05, "max": 0.50},
            "volume_period": {"type": "int", "min": 5, "max": 100},
            "volume_ratio_min": {"type": "float", "min": 0.0, "max": 10.0},
        },
        warmup_bars=180,
    ),
}


def strategy_catalog() -> list[dict]:
    return [s.as_dict() for s in STRATEGIES.values()]


def validate_strategy_params(strategy_id: str, params: dict | None = None) -> dict:
    """Return a typed, bounded parameter set for one strategy.

    Parameters are validated again in the engine even when the caller already
    uses Pydantic. This keeps queued jobs and older API clients from bypassing
    the same limits used by the browser form.
    """
    if strategy_id not in STRATEGIES:
        raise ValueError("strategy_not_found")
    definition = STRATEGIES[strategy_id]
    supplied = dict(params or {})
    unknown = sorted(set(supplied) - set(definition.default_params))
    if unknown:
        raise ValueError(f"unsupported_strategy_parameters:{','.join(unknown)}")
    fixed_parameters = set(definition.default_params) - set(definition.parameter_schema)
    changed_fixed = sorted(
        key for key in fixed_parameters
        if key in supplied and supplied[key] != definition.default_params[key]
    )
    if changed_fixed:
        raise ValueError(f"strategy_parameter_is_fixed:{','.join(changed_fixed)}")
    values = {**definition.default_params, **supplied}
    for key, schema in definition.parameter_schema.items():
        value = values.get(key)
        kind = schema.get("type")
        try:
            if kind == "int":
                value = int(value)
            elif kind == "float":
                value = float(value)
            elif kind == "choice":
                value = str(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid_strategy_parameter:{key}") from exc
        if kind in {"int", "float"}:
            if not math.isfinite(float(value)):
                raise ValueError(f"invalid_strategy_parameter:{key}")
            if schema.get("min") is not None and value < schema["min"]:
                raise ValueError(f"strategy_parameter_below_minimum:{key}")
            if schema.get("max") is not None and value > schema["max"]:
                raise ValueError(f"strategy_parameter_above_maximum:{key}")
        if kind == "choice" and value not in schema.get("options", []):
            raise ValueError(f"invalid_strategy_parameter_choice:{key}")
        values[key] = value

    if strategy_id == "custom_ma_cross" and int(values["fast_period"]) >= int(values["slow_period"]):
        raise ValueError("fast_period_must_be_lower_than_slow_period")
    if strategy_id == "dual_momentum_relative" and int(values["lookback"]) <= int(values["skip_recent"]):
        raise ValueError("dual_momentum_lookback_must_exceed_skipped_period")
    if strategy_id == "rsi14_sma200" and float(values["entry_rsi"]) >= float(values["exit_rsi"]):
        raise ValueError("rsi_entry_must_be_lower_than_exit")
    if strategy_id == "bollinger_rsi_trend" and float(values["entry_rsi"]) >= float(values["exit_rsi"]):
        raise ValueError("rsi_entry_must_be_lower_than_exit")
    return values


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
    formed = avg_gain.notna() & avg_loss.notna()
    # Wilder's expression is mathematically indeterminate when both averages
    # are zero. A flat market has neither buying nor selling pressure, so 50 is
    # the neutral value; only a formed series with gains and no losses is 100.
    rsi = rsi.mask(formed & (avg_gain == 0) & (avg_loss == 0), 50.0)
    rsi = rsi.mask(formed & (avg_gain > 0) & (avg_loss == 0), 100.0)
    return rsi.where(formed)


def _adjusted_high_low(frame: pd.DataFrame, price: pd.Series) -> tuple[pd.Series, pd.Series]:
    high = pd.to_numeric(frame.get("adj_high", frame.get("high", price)), errors="coerce")
    low = pd.to_numeric(frame.get("adj_low", frame.get("low", price)), errors="coerce")
    return high.fillna(price), low.fillna(price)


def _wilder_atr(frame: pd.DataFrame, price: pd.Series, period: int) -> pd.Series:
    high, low = _adjusted_high_low(frame, price)
    previous_close = price.shift(1)
    true_range = pd.concat([
        (high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _supertrend(frame: pd.DataFrame, price: pd.Series, period: int, multiplier: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    high, low = _adjusted_high_low(frame, price)
    atr = _wilder_atr(frame, price, period)
    midpoint = (high + low) / 2.0
    basic_upper = midpoint + multiplier * atr
    basic_lower = midpoint - multiplier * atr
    final_upper = pd.Series(float("nan"), index=price.index, dtype=float)
    final_lower = pd.Series(float("nan"), index=price.index, dtype=float)
    trend = pd.Series(float("nan"), index=price.index, dtype=float)

    first_valid = atr.first_valid_index()
    if first_valid is None:
        return trend, atr, pd.Series(float("nan"), index=price.index, dtype=float)
    start = price.index.get_loc(first_valid)
    final_upper.iloc[start] = basic_upper.iloc[start]
    final_lower.iloc[start] = basic_lower.iloc[start]
    trend.iloc[start] = 1.0 if price.iloc[start] >= midpoint.iloc[start] else 0.0

    for position in range(start + 1, len(price)):
        previous = position - 1
        final_upper.iloc[position] = (
            basic_upper.iloc[position]
            if basic_upper.iloc[position] < final_upper.iloc[previous] or price.iloc[previous] > final_upper.iloc[previous]
            else final_upper.iloc[previous]
        )
        final_lower.iloc[position] = (
            basic_lower.iloc[position]
            if basic_lower.iloc[position] > final_lower.iloc[previous] or price.iloc[previous] < final_lower.iloc[previous]
            else final_lower.iloc[previous]
        )
        if trend.iloc[previous] > 0:
            trend.iloc[position] = 0.0 if price.iloc[position] < final_lower.iloc[position] else 1.0
        else:
            trend.iloc[position] = 1.0 if price.iloc[position] > final_upper.iloc[position] else 0.0

    line = final_lower.where(trend > 0, final_upper)
    return trend, atr, line


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


def build_signal(
    df: pd.DataFrame,
    strategy_id: str,
    params: dict | None = None,
    *,
    benchmark_price: pd.Series | None = None,
) -> tuple[pd.Series, pd.DataFrame, dict]:
    if strategy_id not in STRATEGIES:
        raise ValueError("strategy_not_found")
    definition = STRATEGIES[strategy_id]
    p = validate_strategy_params(strategy_id, params)
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
        high, low = _adjusted_high_low(x, price)
        upper = high.rolling(ep, min_periods=ep).max().shift(1)
        lower = low.rolling(xp, min_periods=xp).min().shift(1)
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

    elif strategy_id == "supertrend_atr":
        atr_period = int(p["atr_period"])
        multiplier = float(p["multiplier"])
        if not 2 <= atr_period <= 200 or not 0.1 <= multiplier <= 20:
            raise ValueError("invalid_supertrend_parameters")
        signal, atr, line = _supertrend(x, price, atr_period, multiplier)
        indicators[f"ATR {atr_period}"] = atr
        indicators["Supertrend"] = line

    elif strategy_id == "dual_momentum_relative":
        lookback = int(p["lookback"])
        skip_recent = int(p.get("skip_recent", 21))
        if lookback <= skip_recent or lookback < 20 or skip_recent < 0:
            raise ValueError("invalid_dual_momentum_periods")
        if benchmark_price is None:
            raise ValueError("benchmark_history_required")
        benchmark = pd.to_numeric(benchmark_price, errors="coerce").reindex(price.index).ffill()
        asset_reference = price.shift(lookback)
        benchmark_reference = benchmark.shift(lookback)
        asset_anchor = price.shift(skip_recent) if skip_recent else price
        benchmark_anchor = benchmark.shift(skip_recent) if skip_recent else benchmark
        asset_return = asset_anchor / asset_reference - 1.0
        benchmark_return = benchmark_anchor / benchmark_reference - 1.0
        excess_return = asset_return - benchmark_return
        absolute_floor = float(p.get("min_absolute_return_pct", 0.0)) / 100.0
        excess_floor = float(p.get("min_excess_return_pct", 0.0)) / 100.0
        valid = asset_return.notna() & benchmark_return.notna()
        indicators["Momentum absoluto %"] = asset_return * 100.0
        indicators["Momentum benchmark %"] = benchmark_return * 100.0
        indicators["Momentum excedente %"] = excess_return * 100.0
        signal = ((asset_return > absolute_floor) & (excess_return > excess_floor)).where(valid)

    elif strategy_id == "bollinger_squeeze_breakout":
        period = int(p["period"])
        stddev = float(p["stddev"])
        squeeze_lookback = int(p["squeeze_lookback"])
        squeeze_quantile = float(p["squeeze_quantile"])
        volume_period = int(p.get("volume_period", 20))
        volume_ratio_min = float(p.get("volume_ratio_min", 1.0))
        if period < 2 or squeeze_lookback < period or not 0 < squeeze_quantile < 1:
            raise ValueError("invalid_bollinger_squeeze_parameters")
        mid = price.rolling(period, min_periods=period).mean()
        deviation = price.rolling(period, min_periods=period).std(ddof=0)
        upper = mid + stddev * deviation
        lower = mid - stddev * deviation
        bandwidth = (upper - lower) / mid.mask(lambda value: value == 0) * 100.0
        threshold = bandwidth.rolling(squeeze_lookback, min_periods=squeeze_lookback).quantile(squeeze_quantile)
        squeeze_previous = bandwidth.shift(1) <= threshold.shift(1)
        breakout = price > upper.shift(1)
        volume = pd.to_numeric(x.get("volume"), errors="coerce")
        average_volume = volume.rolling(volume_period, min_periods=volume_period).mean()
        volume_ratio = volume / average_volume.mask(lambda value: value == 0)
        volume_ok = pd.Series(True, index=x.index, dtype=bool) if volume_ratio_min <= 0 else volume_ratio >= volume_ratio_min
        valid = upper.shift(1).notna() & threshold.shift(1).notna() & volume_ok.notna()
        entry = valid & squeeze_previous & breakout & volume_ok.fillna(False)
        exit_ = mid.notna() & (price < mid)
        signal = _stateful_entry_exit(entry, exit_).where(valid)
        indicators["Bollinger média"] = mid
        indicators["Bollinger inferior"] = lower
        indicators["Bollinger superior"] = upper
        indicators["Bollinger largura %"] = bandwidth
        indicators["Limite do squeeze %"] = threshold
        indicators[f"Volume / média {volume_period}"] = volume_ratio

    else:
        raise ValueError("strategy_not_implemented")

    return signal.astype(float), indicators, p


def warmup_bars(strategy_id: str, params: dict | None = None) -> int:
    if strategy_id not in STRATEGIES:
        raise ValueError("strategy_not_found")
    p = validate_strategy_params(strategy_id, params)
    if strategy_id == "custom_ma_cross":
        return max(int(p["fast_period"]), int(p["slow_period"])) + 20
    if strategy_id == "bollinger_rsi_trend":
        return max(
            int(p["period"]), int(p.get("rsi_period", 14)),
            int(p["trend_period"]) + int(p.get("trend_slope_lookback", 20)),
        ) + 20
    if strategy_id == "rsi14_sma200":
        return max(int(p["rsi_period"]), int(p["trend_period"])) + 20
    if strategy_id == "macd_12_26_9":
        return int(p["slow"]) + int(p["signal"]) + 20
    if strategy_id == "donchian_20_10":
        return max(int(p["entry_period"]), int(p["exit_period"])) + 10
    if strategy_id == "momentum_12m":
        return int(p["lookback"]) + 20
    if strategy_id == "supertrend_atr":
        return int(p["atr_period"]) * 3 + 20
    if strategy_id == "dual_momentum_relative":
        return int(p["lookback"]) + 20
    if strategy_id == "bollinger_squeeze_breakout":
        return int(p["squeeze_lookback"]) + int(p["period"]) + 20
    return max(STRATEGIES[strategy_id].warmup_bars, max(
        (int(value) for key, value in p.items() if "period" in key and isinstance(value, (int, float))),
        default=0,
    ) + 20)
