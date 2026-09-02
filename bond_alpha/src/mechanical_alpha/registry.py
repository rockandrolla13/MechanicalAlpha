"""Alpha index.

The registry points to standalone alpha files.
It does not implement formulas.
"""

from __future__ import annotations

from dataclasses import dataclass

from mechanical_alpha.availability import FactorSpec


@dataclass(frozen=True)
class AlphaFile:
    """Index entry for a standalone alpha module."""

    alpha_id: str
    name: str
    module: str
    status: str


ALPHA_INDEX: tuple[AlphaFile, ...] = (
    AlphaFile("A1", "RFQ count imbalance", "mechanical_alpha.alphas.A1_rfq_count_imbalance", "implemented"),
    AlphaFile("A2", "RFQ notional imbalance", "mechanical_alpha.alphas.A2_rfq_notional_imbalance", "implemented"),
    AlphaFile("A3", "Buy/sell intensity pressure", "mechanical_alpha.alphas.A3_buy_sell_intensity", "implemented"),
    AlphaFile("A4", "Last-side persistence and switching state", "mechanical_alpha.alphas.A4_last_side_persistence", "implemented"),
    AlphaFile("A5", "Multi-clock activity surprise", "mechanical_alpha.alphas.A5_activity_surprise", "implemented"),
    AlphaFile("A6", "Spread-conditioned flow pressure", "mechanical_alpha.alphas.A6_spread_conditioned_flow", "implemented"),
    AlphaFile("A16", "RFQ scarcity and disagreement", "mechanical_alpha.alphas.A16_rfq_scarcity_disagreement", "implemented"),
    AlphaFile("T1", "Triplet momentum/reversal", "mechanical_alpha.alphas.T1_triplet_momentum_reversal", "implemented"),
    AlphaFile("BOND_CARRY_ROLLDOWN", "Bond carry/roll-down from par-adjusted spread curve", "mechanical_alpha.alphas.BOND_carry_rolldown", "implemented"),
    AlphaFile("ETF_OPT_POSITIONING", "FI ETF options positioning", "mechanical_alpha.alphas.ETF_options_positioning", "implemented"),
    AlphaFile("ETF_OPT_OI_CHANGE", "FI ETF options open-interest change", "mechanical_alpha.alphas.ETF_options_positioning", "implemented"),
    AlphaFile("ETF_OPT_VOLUME_PRESSURE", "FI ETF options volume pressure", "mechanical_alpha.alphas.ETF_options_positioning", "implemented"),
    AlphaFile("ETF_OPT_DEALER_GREEKS", "FI ETF options dealer greek exposure", "mechanical_alpha.alphas.ETF_options_positioning", "implemented"),
    AlphaFile("ETF_OPT_COMPOSITE", "FI ETF options positioning composite", "mechanical_alpha.alphas.ETF_options_positioning", "implemented"),
    AlphaFile("FX_MOM", "Cookbook price momentum primitives", "mechanical_alpha.fx_cookbook.momentum", "component_only"),
    AlphaFile("FX_CARRY", "Cookbook carry", "mechanical_alpha.fx_cookbook.carry", "blocked_human"),
    AlphaFile("FX_VALUE", "Cookbook fundamental value", "mechanical_alpha.fx_cookbook.value", "blocked_human"),
    AlphaFile("RATES_SPILLOVER", "Rates momentum spill-over", "mechanical_alpha.fx_cookbook.rates_momentum_spillover", "blocked_missing_data"),
    AlphaFile("COFFEE_DTCC", "COFFEE/DTCC positioning primitives", "mechanical_alpha.fx_cookbook.coffee", "component_only"),
    AlphaFile("CFTC_CONT", "CFTC continuation", "mechanical_alpha.fx_cookbook.cftc_continuation", "blocked_missing_data"),
    AlphaFile("CFTC_REV", "CFTC reversal", "mechanical_alpha.fx_cookbook.cftc_reversal", "blocked_human"),
)


ALPHA_SPECS: tuple[FactorSpec, ...] = (
    FactorSpec("A1", "Clock Seasonality Alpha", ("prediction_timestamp", "price"), notes="TRACE proxy only without RFQs."),
    FactorSpec("A2", "Triplet Momentum/Reversal Alpha", ("fair_value",)),
    FactorSpec("A3", "Variance-Ratio Reversal Alpha", ("fair_value",)),
    FactorSpec("A4", "Last-Side Persistence and Future CR01 Flow Alpha", ("side",), optional_fields=("cr01",), notes="Standalone fitted A4 uses train-only logistic next-side and ridge future signed-CR01-flow models."),
    FactorSpec("A5", "Fitted Activity Surprise Alpha", ("prediction_timestamp",), optional_fields=("notional", "dv01", "cr01", "issuer_id"), notes="Standalone fitted A5 compares observed bond and issuer activity to frozen train-period population baselines."),
    FactorSpec("A6", "Spread-Conditioned Flow Pressure Alpha", ("side", "notional", "spread"), optional_fields=("cr01", "bid", "ask", "mid", "source_disagreement"), notes="Standalone fitted A6 interacts prior flow pressure with as-of composite liquidity state."),
    FactorSpec("A7", "Curve-To-Level Spillover Alpha", ("issuer_id", "maturity_date", "fair_value")),
    FactorSpec("A8", "Bond Curve Residual Alpha", ("issuer_id", "maturity_date", "fair_value")),
    FactorSpec("A9", "PC Residual Momentum Alpha", ("issuer_curve_pc_residual",)),
    FactorSpec("A10", "Roll-Down / Carry-Adjusted Curve Alpha", ("maturity_date", "coupon", "duration")),
    FactorSpec("A11", "Issuer News Sentiment Alpha", ("issuer_news_sentiment",)),
    FactorSpec("A12", "News Volume Conditioning Alpha", ("issuer_news_volume",)),
    FactorSpec("A13", "Macro Sentiment Regime Interaction", ("macro_sentiment",)),
    FactorSpec("A14", "Transient Theme Factor Alpha", ("theme_exposure", "theme_factor")),
    FactorSpec("A15", "Covariance-Regime-Conditioned Alpha", ("price", "external_factor_value")),
    FactorSpec("A16", "RFQ Scarcity and Disagreement Alpha", ("rfq_id", "timestamp"), optional_fields=("response_count", "number_of_dealers", "quote_dispersion", "response_latency_ms", "responded", "firmed_up", "executed"), notes="Standalone fitted A16 measures dealer response scarcity, quote disagreement, latency, and RFQ conversion quality."),
    FactorSpec("B1", "Last-trade sign", ("side",)),
    FactorSpec("B2", "Signed-spread interaction", ("side", "spread")),
    FactorSpec("B3", "Exponentially decayed signed flow", ("side", "notional")),
    FactorSpec("B4", "Per-type Hawkes intensity covariates", ("prediction_timestamp", "side")),
    FactorSpec("B5", "Buy/sell separated print streams and gap", ("side", "price", "notional")),
    FactorSpec("B6", "Best-quote imbalance", ("bid", "ask", "bid_size", "ask_size")),
    FactorSpec("B7", "Multi-level book-pressure grid", ("dealer_quote_levels",)),
    FactorSpec("B8", "Event-signed quote-change OFI", ("quote_update_event",)),
    FactorSpec("B9", "Moving-average deviation reversal", ("price", "notional")),
    FactorSpec("B10", "Volume-conditioned reversal", ("price", "notional", "amount_outstanding")),
    FactorSpec("B11", "Range-position reversal", ("price",)),
    FactorSpec("B12", "Conditional reversal/momentum switch", ("price", "spread")),
    FactorSpec("B13", "Impact-state de-pressured value", ("side", "notional", "price")),
    FactorSpec("B14", "Price-volume rank divergence", ("price", "notional")),
    FactorSpec("B15", "Trade-price percentiles", ("price",)),
    FactorSpec("T1", "Triplet Momentum/Reversal", ("prediction_timestamp", "price"), optional_fields=("fair_value",), notes="Fitted on train clock panels and scored with frozen selected triplets."),
    FactorSpec("ETF_OPT_POSITIONING", "FI ETF Options Positioning", ("external_factors:etf_option_position",), optional_fields=("external_factors:etf_bond_lookthrough_weight",), notes="Computes OI-change, volume-pressure, dealer-greek, composite, and optional ETF-to-bond lookthrough signals."),
    FactorSpec("ETF_OPT_OI_CHANGE", "FI ETF Options Open-Interest Change", ("external_factors:etf_option_position",), optional_fields=("external_factors:etf_bond_lookthrough_weight",), notes="Slow options positioning component using point-in-time open-interest changes."),
    FactorSpec("ETF_OPT_VOLUME_PRESSURE", "FI ETF Options Volume Pressure", ("external_factors:etf_option_position",), optional_fields=("external_factors:etf_bond_lookthrough_weight",), notes="Fast option-flow component using point-in-time option volume."),
    FactorSpec("ETF_OPT_DEALER_GREEKS", "FI ETF Options Dealer Greek Exposure", ("external_factors:etf_option_position",), optional_fields=("external_factors:etf_bond_lookthrough_weight",), notes="Hedging-pressure component using direct dealer greek exposure when provided, with an explicit chain-derived fallback."),
    FactorSpec("ETF_OPT_COMPOSITE", "FI ETF Options Composite", ("external_factors:etf_option_position",), optional_fields=("external_factors:etf_bond_lookthrough_weight",), notes="Transparent mean of finite ETF option positioning components."),
    FactorSpec("FX_MOM", "Cookbook Price Momentum", ("price",), optional_fields=("fair_value",), notes="Component primitives implemented; source-literal variants require MOM-001/MOM-002 choices."),
    FactorSpec("BOND_CARRY_ROLLDOWN", "Bond Carry/Roll-Down from Par-Adjusted Spread Curve", ("external_factors:par_adjusted_spread_curve",), notes="Bond-native adapter following Martin arXiv:2201.01330; computes carry, roll-down, RV, and total return from a point-in-time curve table."),
    FactorSpec("FX_CARRY", "Cookbook Carry", ("fx_forward", "financing_curve"), notes="Source-literal FX carry remains blocked pending CARRY-001/CARRY-002/CARRY-003; bond adapter is BOND_CARRY_ROLLDOWN."),
    FactorSpec("FX_VALUE", "Cookbook Fundamental Value", ("reer", "fundamental_value_panel"), notes="Source-literal FX value remains blocked pending VALUE-001; bond par-adjusted curve RV adapter is BOND_CARRY_ROLLDOWN."),
    FactorSpec("RATES_SPILLOVER", "Rates Momentum Spill-Over", ("external_factors:rates", "curve_changes"), notes="Blocked unless PIT rate-factor inputs are provided."),
    FactorSpec("COFFEE_DTCC", "COFFEE/DTCC Positioning Primitives", ("option_delta", "option_ttm", "call_put_notional"), notes="Primitive source logic is available through ETF_OPT_POSITIONING when point-in-time options fields are supplied."),
    FactorSpec("CFTC_CONT", "CFTC Continuation", ("cftc_report_date", "cftc_net_position"), notes="Blocked because CFTC COT reports are not in the current public bond bundle."),
    FactorSpec("CFTC_REV", "CFTC Reversal", ("cftc_report_date", "cftc_net_position"), notes="Blocked pending CFTC-R-001 and CFTC COT reports."),
)


def standalone_alpha_index() -> list[AlphaFile]:
    return list(ALPHA_INDEX)


def default_registry() -> list[FactorSpec]:
    return list(ALPHA_SPECS)
