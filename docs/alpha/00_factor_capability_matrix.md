# Factor Capability Matrix

Date: 2026-08-30

Audit interpretation:

- `A1-A16` means Alpha Families 1-16 from `anonymous_rfq_alpha_feature_research_spec_from_quantcraft.md`.
- `B1-B15` means factors F1-F15 from `bond_alpha_factors.md`.
- The repo does not contain literal `A1-A16` or `B1-B15` labels.

Availability labels:

- directly available: field exists and semantics are usable now
- derivable: can be computed from available fields with documented assumptions
- partially available: some required inputs exist, but an important field or timing guarantee is missing
- unavailable: no source found
- ambiguous: field exists, but semantics must be validated

## A-Family Matrix

| ID | Factor | Required Inputs | Capability | Reason |
| --- | --- | --- | --- | --- |
| A1 | Clock Seasonality Alpha | RFQ or prediction timestamp, bucket, future return | partially available | TRACE timestamps and future trade-price returns exist. True RFQ timestamps and as-of fair-value returns do not. |
| A2 | Triplet Momentum/Reversal Alpha | FV/spread/residual series, lag, vantage, horizon | partially available | Trade-price proxy can be built. FV, spread, and residual targets are not confirmed. |
| A3 | Variance-Ratio Reversal Alpha | FV, spread, or residual return series | partially available | Trade-price returns are derivable. Preferred FV/spread/residual series are missing. |
| A4 | Low-Volatility Reversal Alpha | returns, volatility, reversal signal | derivable | Can use TRACE trade-price proxy. Needs sparse/stale handling. |
| A5 | Risk-Appetite-Conditioned Reversal Alpha | reversal signal plus CDX/ETF/rates/risk regime | partially available | LQD/HYG/JNK order-book data exists. CDX, VIX, MOVE not confirmed. |
| A6 | Curve PCA Momentum Alpha | issuer/sector curve points, maturity, spread/yield | partially available | Many same-issuer CUSIPs exist, but maturity and clean curve fields are missing. |
| A7 | Curve-To-Level Spillover Alpha | curve move and single-bond level | partially available | Issuer families exist. Curve construction needs maturity or tenors. |
| A8 | Bond Curve Residual Alpha | bond residual vs issuer curve | partially available | Issuer grouping exists. Curve residuals need maturity and fair value. |
| A9 | PC Residual Momentum Alpha | curve PCA residuals | unavailable | PCA residuals require curve metadata and stable fair values. |
| A10 | Roll-Down / Carry-Adjusted Curve Alpha | curve, maturity, carry/rolldown | unavailable | Maturity, coupon, curve, and spread duration are missing. |
| A11 | Issuer News Sentiment Alpha | issuer news timestamps, sentiment | unavailable | No news source found. |
| A12 | News Volume Conditioning Alpha | news volume and base alpha | unavailable | No news source found. |
| A13 | Macro Sentiment Regime Interaction | macro sentiment/risk regime and base alpha | unavailable | No macro sentiment source found. ETF regime is only a partial substitute. |
| A14 | Transient Theme Factor Alpha | theme exposure and theme/news factor | unavailable | No theme or news exposure source found. |
| A15 | Covariance-Regime-Conditioned Alpha | covariance/correlation regimes | partially available | ETF/rates order-book data exists. Bond-level fair-value returns are not confirmed. |
| A16 | Flow-Confirmed Triplet Alpha | RFQ flow plus triplet pattern | partially available | TRACE signed flow exists. True RFQ flow and FV triplets do not. |

## B-Factor Matrix

| ID | Factor | Required Inputs | Capability | Reason |
| --- | --- | --- | --- | --- |
| B1 | Last-trade sign | signed print stream | ambiguous | `rpt_side_cd` exists. Perspective must be validated before using the sign. |
| B2 | Signed-spread interaction | sign and spread | partially available | Sign exists ambiguously. Bond spread/composite spread is missing. |
| B3 | Exponentially decayed signed flow | signed prints and volume | ambiguous | Timestamp, side, and size exist. Side perspective and size units are unresolved. |
| B4 | Per-type Hawkes intensity covariates | event times by side/type | derivable | TRACE event times and side/type fields exist. Must handle interdealer double reports. |
| B5 | Buy/sell separated print streams and gap | side, price, volume | ambiguous | Side, price, volume exist. Effective spread meaning depends on side convention. |
| B6 | Best-quote imbalance | bid/ask sizes or RFQ/quote axes | unavailable | No bond-level composite quote or dealer axes source found. |
| B7 | Multi-level book-pressure grid | dealer-level quote sizes | unavailable | ETF books exist, but not bond dealer axes. |
| B8 | Event-signed quote-change OFI | bond quote updates | unavailable | No bond quote-update stream found. |
| B9 | Moving-average deviation reversal | price, EMA/VWAP | derivable | TRACE trade-price proxy supports it. Must record stale-window source. |
| B10 | Volume-conditioned reversal | price returns and abnormal volume | partially available | Price and size exist. Amount outstanding is missing for preferred scaling. |
| B11 | Range-position reversal | rolling min/max price | derivable | TRACE price history supports it with sparse-window controls. |
| B12 | Conditional reversal/momentum switch | price vs VWAP and spread threshold | partially available | Price/VWAP derivable. Typical bid-offer spread is missing. |
| B13 | Impact-state de-pressured value | signed flow, price, future returns | ambiguous | Can estimate from TRACE if sign is validated. No true fair value. |
| B14 | Price-volume rank divergence | price and volume ranks | derivable | TRACE price and size support weekly/event bars. |
| B15 | Trade-price percentiles | recent trade prices by side/all | ambiguous | Prices exist. Side-specific percentiles depend on side validation. |

## Factors Buildable Immediately

These can be prototyped from TRACE after a side-convention decision:

- B4 Per-type Hawkes intensity covariates
- B9 Moving-average deviation reversal
- B11 Range-position reversal
- B14 Price-volume rank divergence
- A4 Low-volatility reversal using trade-price proxy
- A1 Clock seasonality using TRACE print timestamps and trade-price proxy labels

These can be prototyped, but should be marked weaker:

- B1 Last-trade sign
- B3 Decayed signed flow
- B5 Buy/sell separated streams
- B10 Volume-conditioned reversal
- B13 Impact-state de-pressured value
- B15 Trade-price percentiles
- A2 Triplet momentum/reversal using trade-price proxy
- A3 Variance-ratio reversal using trade-price proxy
- A16 Flow-confirmed triplet using TRACE flow, not RFQ flow

## Factors Blocked By Missing Data

- A9 PC residual momentum
- A10 Roll-down / carry-adjusted curve alpha
- A11 Issuer news sentiment alpha
- A12 News volume conditioning alpha
- A13 Macro sentiment regime interaction
- A14 Transient theme factor alpha
- B6 Best-quote imbalance
- B7 Multi-level book-pressure grid
- B8 Event-signed quote-change OFI

## Factors Requiring External Or Reference Data

- A5 needs CDX, VIX/MOVE, or a validated ETF/rates proxy.
- A6, A7, A8, and A15 need maturity/rating/sector/duration and fair-value or spread construction.
- B2 and B12 need bond-level bid/ask spread or a defensible realized-spread proxy.

## Sign-Convention Warning

`AGENTS.md` defines dealer perspective:

```text
side_t = +1 means client sells bond to dealer
side_t = -1 means client buys bond from dealer
```

`bond_alpha_factors.md` defines TRACE-style:

```text
d_k = +1 means customer buy
d_k = -1 means customer sell
```

`bondsim` currently documents:

```text
BUY = +1
SELL = -1 using TRACE rpt_side_cd mapping
```

This must be resolved before implementing signed alpha factors.

