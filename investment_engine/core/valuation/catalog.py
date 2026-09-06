"""Canonical valuation families and their asset-class applicability.

This module deliberately separates a *family* (the investor question) from a
calculation method.  For example, DCF and Gordon/DDM are both economic-value
methods, while a future contract belongs to a fair-value/carry engine rather
than to traditional business valuation.

Legacy identifiers remain accepted so stored snapshots and existing API
clients do not need to migrate in lockstep with the presentation names.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValuationFamily:
    id: str
    label: str
    description: str
    filter_key: str
    permission_key: str


@dataclass(frozen=True)
class ValuationMethodMetadata:
    canonical_id: str
    family_id: str
    label: str
    version: str
    legacy_ids: tuple[str, ...] = ()
    formula: str = ""
    required_inputs: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Applicability:
    status: str
    method: str | None
    note: str


VALUATION_FAMILIES: dict[str, ValuationFamily] = {
    "graham_reference": ValuationFamily(
        id="graham_reference",
        label="Número de Graham",
        description="Referência conservadora baseada em lucro e patrimônio positivos.",
        filter_key="below_graham",
        permission_key="can_use_graham_valuation",
    ),
    "dividend_yield_ceiling": ValuationFamily(
        id="dividend_yield_ceiling",
        label="Preço-teto por dividend yield-alvo",
        description="Preço compatível com um rendimento mínimo e proventos sustentáveis.",
        filter_key="below_dividend_yield_ceiling",
        permission_key="can_use_dividend_ceiling",
    ),
    "relative_peers": ValuationFamily(
        id="relative_peers",
        label="Valuation relativo por pares",
        description="Compara múltiplos com empresas ou fundos realmente comparáveis.",
        filter_key="below_relative_value",
        permission_key="can_use_relative_valuation",
    ),
    "economic_value": ValuationFamily(
        id="economic_value",
        label="Valor econômico por classe",
        description="Usa o fluxo ou o ativo econômico apropriado a cada classe.",
        filter_key="below_economic_value",
        permission_key="can_use_economic_valuation",
    ),
}


VALUATION_METHODS: dict[str, ValuationMethodMetadata] = {
    "graham_number": ValuationMethodMetadata(
        canonical_id="graham_number",
        family_id="graham_reference",
        label="Número de Graham",
        version="1.0",
        legacy_ids=("graham", "graham_price", "preco_justo_graham"),
        formula="sqrt(22.5 * EPS * BVPS)",
        required_inputs=("earnings_per_share", "book_value_per_share"),
        note="Não deve ser apresentado como um preço justo universal.",
    ),
    "dividend_yield_ceiling_ttm": ValuationMethodMetadata(
        canonical_id="dividend_yield_ceiling_ttm",
        family_id="dividend_yield_ceiling",
        label="Preço-teto por dividend yield-alvo (proventos de 12 meses)",
        version="1.0",
        legacy_ids=(
            "dividend_yield_target", "dividend_target_price",
            "barsi_ceiling_price", "bazin_ceiling_price", "barsi", "bazin",
        ),
        formula="dividend_per_share_ttm / (target_yield_pct / 100)",
        required_inputs=("dividend_per_share_ttm", "target_yield_pct"),
        note="O nome Bazin somente é adequado quando há normalização histórica dos proventos.",
    ),
    "relative_peers": ValuationMethodMetadata(
        canonical_id="relative_peers",
        family_id="relative_peers",
        label="Valuation relativo por pares",
        version="1.0",
        legacy_ids=("peer_valuation", "relative_valuation"),
        formula="median(peer_multiple_scenario * target_fundamental_per_share)",
        required_inputs=("market_price", "peer_group", "peer_multiples"),
    ),
    "gordon_growth_ddm": ValuationMethodMetadata(
        canonical_id="gordon_growth_ddm",
        family_id="economic_value",
        label="Modelo de Gordon (DDM)",
        version="2.0",
        legacy_ids=("gordon_growth",),
        formula="D1 / (required_return - stable_growth)",
        required_inputs=("normalized_dividend_per_share_d0", "required_return_pct", "growth_pct"),
        note="Exige retorno requerido e crescimento explícitos para cada cenário.",
    ),
    "gordon_ddm_ceiling": ValuationMethodMetadata(
        canonical_id="gordon_ddm_ceiling",
        family_id="economic_value",
        label="Preço-limite pelo Modelo de Gordon (DDM)",
        version="2.0",
        legacy_ids=(),
        formula="gordon_value * (1 - margin_of_safety_pct / 100)",
        required_inputs=("gordon_value", "margin_of_safety_pct"),
    ),
    "economic_value_by_class": ValuationMethodMetadata(
        canonical_id="economic_value_by_class",
        family_id="economic_value",
        label="Valor econômico por classe",
        version="1.0",
        required_inputs=("asset_type", "asset_class", "class_specific_financials"),
    ),
    "etf_nav_reference": ValuationMethodMetadata(
        canonical_id="etf_nav_reference",
        family_id="economic_value",
        label="Referência patrimonial do ETF (NAV)",
        version="1.0",
        formula="market_price / (1 + premium_discount_pct / 100)",
        required_inputs=("market_price", "nav_discount_premium_pct"),
        note="Compara a cota com o patrimônio líquido por cota informado pela fonte.",
    ),
    "etf_peer_nav_premium": ValuationMethodMetadata(
        canonical_id="etf_peer_nav_premium",
        family_id="relative_peers",
        label="Prêmio/desconto relativo ao NAV dos ETFs pares",
        version="1.0",
        formula="target_nav * (1 + peer_premium_discount_pct / 100)",
        required_inputs=("target_nav", "peer_nav_discount_premiums"),
    ),
    "bdr_pbv_peers": ValuationMethodMetadata(
        canonical_id="bdr_pbv_peers",
        family_id="relative_peers",
        label="Valuation relativo P/VP entre BDRs comparáveis",
        version="1.0",
        formula="book_value_per_bdr * peer_pbv",
        required_inputs=("market_price", "book_value_per_bdr", "peer_pbv"),
        note="Usa apenas BDRs do mesmo setor ou indústria e não reaproveita P/L possivelmente incompatível.",
    ),
    "bdr_underlying_parity": ValuationMethodMetadata(
        canonical_id="bdr_underlying_parity",
        family_id="economic_value",
        label="Paridade do BDR com o ativo-lastro",
        version="1.0",
        formula="underlying_price * brl_fx * underlying_shares_per_bdr",
        required_inputs=("underlying_price", "brl_fx", "underlying_shares_per_bdr"),
    ),
    "future_cost_of_carry": ValuationMethodMetadata(
        canonical_id="future_cost_of_carry",
        family_id="economic_value",
        label="Preço teórico do futuro por custo de carregamento",
        version="1.0",
        legacy_ids=("fair_value_cost_of_carry",),
        formula="spot * ((1 + carry_rate) / (1 + income_yield)) ** (days / 365)",
        required_inputs=("spot_price", "carry_rate", "days_to_expiry"),
        note="Aplicado somente quando contrato frontal, vencimento e ativo à vista são identificados.",
    ),
}


_METHOD_ALIASES = {
    alias.casefold(): canonical
    for canonical, metadata in VALUATION_METHODS.items()
    for alias in (canonical, *metadata.legacy_ids)
}


def valuation_method_metadata(method: str) -> ValuationMethodMetadata:
    """Return canonical metadata while accepting every historical identifier."""
    key = str(method or "").strip().casefold()
    canonical = _METHOD_ALIASES.get(key)
    if canonical is None:
        raise KeyError(f"unknown_valuation_method:{method}")
    return VALUATION_METHODS[canonical]


def normalize_valuation_method(method: str) -> str:
    return valuation_method_metadata(method).canonical_id


def method_metadata_dict(method: str) -> dict:
    metadata = valuation_method_metadata(method)
    return {
        **asdict(metadata),
        "legacy_method": str(method),
    }


def _rule(status: str, method: str | None, note: str) -> Applicability:
    return Applicability(status=status, method=method, note=note)


NA = _rule("not_applicable", None, "Esta família não representa corretamente a classe.")


VALUATION_APPLICABILITY: dict[str, dict[str, dict[str, Applicability]]] = {
    "stock": {
        "default": {
            "graham_reference": _rule("conditional", "graham_number", "Somente com lucro e patrimônio positivos e recorrentes."),
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Somente para pagadoras com proventos sustentáveis."),
            "relative_peers": _rule("supported", "relative_peers", "Usar pares do mesmo setor, risco e perfil de crescimento."),
            "economic_value": _rule("requires_data", "dcf_fcff_fcfe", "Requer fluxos, balanço, ações e custo de capital."),
        },
        "bank": {
            "graham_reference": _rule("conditional", "graham_number", "Apenas como referência secundária; capital regulatório exige contexto."),
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Exige payout e capital regulatório sustentáveis."),
            "relative_peers": _rule("supported", "pbv_peers", "Comparar P/VP apenas entre bancos; ROE, crescimento e risco permanecem filtros de qualidade separados."),
            "economic_value": _rule("requires_data", "fcfe_ddm", "FCFE/DDM é preferível a FCFF/EV-EBITDA para bancos."),
        },
        "insurance": {
            "graham_reference": _rule("conditional", "graham_number", "Somente como referência secundária."),
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Exige distribuição recorrente e solvência."),
            "relative_peers": _rule("supported", "pbv_peers", "Comparar P/VP apenas entre seguradoras; ROE, crescimento e solvência permanecem filtros separados."),
            "economic_value": _rule("requires_data", "fcfe_ddm", "Requer fluxos ao acionista e premissas de solvência."),
        },
    },
    "fii": {
        "default": {
            "graham_reference": NA,
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Rendimento é auxiliar e deve ser normalizado."),
            "relative_peers": _rule("supported", "relative_peers", "Comparar apenas fundos do mesmo segmento e estrutura."),
            "economic_value": _rule("requires_data", "nav_noi_cap_rate", "Classificar o fundo antes de escolher o modelo econômico."),
        },
        "brick": {
            "graham_reference": NA,
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Usar AFFO/renda recorrente, não distribuição atípica."),
            "relative_peers": _rule("supported", "relative_peers", "P/NAV e FFO yield entre fundos do mesmo segmento."),
            "economic_value": _rule("requires_data", "nav_noi_cap_rate", "NAV ajustado, NOI/cap rate e AFFO."),
        },
        "paper": {
            "graham_reference": NA,
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Separar renda recorrente de inflação e amortizações."),
            "relative_peers": _rule("supported", "relative_peers", "Comparar indexador, risco, duration e LTV semelhantes."),
            "economic_value": _rule("requires_data", "credit_portfolio_dcf", "Carteira de CRI, spread, duration, garantias e perdas esperadas."),
        },
        "fof": {
            "graham_reference": NA,
            "dividend_yield_ceiling": _rule("conditional", "dividend_yield_ceiling_ttm", "Renda recorrente é apenas confirmação."),
            "relative_peers": _rule("supported", "relative_peers", "Comparar desconto e custos com FOFs semelhantes."),
            "economic_value": _rule("requires_data", "look_through_nav", "NAV look-through da carteira menos despesas e passivos."),
        },
    },
    "etf": {
        "default": {
            "graham_reference": NA,
            "dividend_yield_ceiling": NA,
            "relative_peers": _rule("conditional", "etf_peer_nav_premium", "Usa prêmio/desconto ao NAV entre ETFs na mesma moeda quando há amostra suficiente."),
            "economic_value": _rule("conditional", "etf_nav_reference", "Usa NAV por cota ou prêmio/desconto ao NAV efetivamente informado pela fonte."),
        },
    },
    "bdr": {
        "default": {
            "graham_reference": _rule("requires_data", "underlying_graham", "Calcular no ativo-lastro e converter pela razão e câmbio."),
            "dividend_yield_ceiling": _rule("requires_data", "underlying_dividend_ceiling", "Usar proventos do lastro, tributação, razão e câmbio."),
            "relative_peers": _rule("conditional", "bdr_pbv_peers", "Compara P/VP somente entre BDRs do mesmo setor ou indústria quando há amostra suficiente."),
            "economic_value": _rule("requires_data", "bdr_underlying_parity", "Valor do lastro multiplicado por câmbio e razão verificada do programa."),
        },
        "etf": {
            "graham_reference": NA,
            "dividend_yield_ceiling": NA,
            "relative_peers": _rule("requires_data", "underlying_etf_look_through", "Requer carteira do ETF estrangeiro."),
            "economic_value": _rule("requires_data", "underlying_nav_fx_ratio", "NAV do ETF, câmbio e razão do BDR."),
        },
    },
    "future": {
        "default": {
            "graham_reference": NA,
            "dividend_yield_ceiling": NA,
            "relative_peers": NA,
            "economic_value": _rule("conditional", "future_cost_of_carry", "Calcula o preço teórico quando ativo à vista, taxa de carrego e vencimento do contrato frontal estão disponíveis."),
        },
    },
}


def valuation_applicability(asset_type: str, asset_class: str | None = None) -> dict[str, Applicability]:
    """Return all four family rules for an asset type/class.

    Unknown classes fall back to that asset type's explicit ``default`` rule;
    unknown asset types fail closed instead of receiving an unsuitable model.
    """
    type_key = str(asset_type or "").strip().casefold()
    classes = VALUATION_APPLICABILITY.get(type_key)
    if classes is None:
        return {family_id: NA for family_id in VALUATION_FAMILIES}
    class_key = str(asset_class or "default").strip().casefold()
    rules = classes.get(class_key) or classes["default"]
    return {family_id: rules[family_id] for family_id in VALUATION_FAMILIES}


def applicability_dict(asset_type: str, asset_class: str | None = None) -> dict[str, dict]:
    return {
        family_id: asdict(rule)
        for family_id, rule in valuation_applicability(asset_type, asset_class).items()
    }
