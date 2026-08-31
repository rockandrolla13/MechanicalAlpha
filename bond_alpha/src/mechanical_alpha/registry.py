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
)


ALPHA_SPECS: tuple[FactorSpec, ...] = (
    FactorSpec("A1", "Clock Seasonality Alpha", ("prediction_timestamp", "price"), notes="TRACE proxy only without RFQs."),
    FactorSpec("A2", "Triplet Momentum/Reversal Alpha", ("fair_value",)),
    FactorSpec("A3", "Variance-Ratio Reversal Alpha", ("fair_value",)),
    FactorSpec("A4", "Low-Volatility Reversal Alpha", ("price",)),
    FactorSpec("A5", "Risk-Appetite-Conditioned Reversal Alpha", ("price", "external_factor_value")),
    FactorSpec("A6", "Curve PCA Momentum Alpha", ("issuer_id", "maturity_date", "yield")),
    FactorSpec("A7", "Curve-To-Level Spillover Alpha", ("issuer_id", "maturity_date", "fair_value")),
    FactorSpec("A8", "Bond Curve Residual Alpha", ("issuer_id", "maturity_date", "fair_value")),
    FactorSpec("A9", "PC Residual Momentum Alpha", ("issuer_curve_pc_residual",)),
    FactorSpec("A10", "Roll-Down / Carry-Adjusted Curve Alpha", ("maturity_date", "coupon", "duration")),
    FactorSpec("A11", "Issuer News Sentiment Alpha", ("issuer_news_sentiment",)),
    FactorSpec("A12", "News Volume Conditioning Alpha", ("issuer_news_volume",)),
    FactorSpec("A13", "Macro Sentiment Regime Interaction", ("macro_sentiment",)),
    FactorSpec("A14", "Transient Theme Factor Alpha", ("theme_exposure", "theme_factor")),
    FactorSpec("A15", "Covariance-Regime-Conditioned Alpha", ("price", "external_factor_value")),
    FactorSpec("A16", "Flow-Confirmed Triplet Alpha", ("side", "notional", "fair_value")),
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
)


def standalone_alpha_index() -> list[AlphaFile]:
    return list(ALPHA_INDEX)


def default_registry() -> list[FactorSpec]:
    return list(ALPHA_SPECS)
