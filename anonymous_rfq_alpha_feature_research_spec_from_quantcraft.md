# Anonymous Corporate Bond RFQ Alpha Feature Research Specification

## 0. Purpose

This document specifies a set of **alpha-prediction features** that can be extracted or adapted from the attached Quantcraft-style papers and applied to anonymous corporate bond RFQ data.

The purpose is not to build a quote optimizer. The purpose is to create features that predict:

```text
future bond fair-value return
future spread return
future factor-residual return
```

The core target is:

```text
Alpha_{i,t,h} = E[R_{i,t,h} | Information available at time t]
```

where:

```text
i = bond / ISIN
t = RFQ timestamp or prediction timestamp
h = forecast horizon
R_{i,t,h} = future return over horizon h
```

The attached papers are not corporate-bond RFQ papers. The useful transfer is at the level of **alpha operators**:

1. clock seasonality,
2. lag-vantage-horizon pattern mining,
3. momentum versus reversal classification,
4. variance-ratio reversal,
5. curve PCA momentum,
6. curve-to-level spillover,
7. residual momentum,
8. sentiment / news regime interaction,
9. news volume as a signal-strength modifier,
10. covariance / correlation regime conditioning.

This document describes how to translate those operators into anonymous corporate bond alpha features.

---

## 1. Source Paper Triage

## 1.1 High-Value Sources

| Source | Alpha Operators To Extract | Corporate Bond Translation |
|---|---|---|
| The Intraday Lab: Trading the Clock | clock-seasonality signal, t-stat heatmaps, lookback/lookahead grid, multiple-testing control | time-of-day RFQ alpha, session effects, predictable mark drift by clock bucket |
| The Intraday Lab: Catching the Beat | triplets, lag-vantage-horizon momentum/reversal, Spearman rank pattern mining | lagged FV / spread / flow patterns predicting future FV returns |
| Speeding Into The Curve | curve PCA, curve momentum, PC residual momentum, curve-to-level spillover | issuer curve PCA, sector curve PCA, maturity-bucket spillover |
| Gearing into Reverse | variance-ratio reversal, low-vol reversal, risk-appetite-conditioned reversal | mean-reversion features on bond residuals, issuer residuals, CDX-adjusted marks |

## 1.2 Conditional Sources

| Source | Use If You Have | Corporate Bond Translation |
|---|---|---|
| Catching the sentiment waves | macro/news sentiment or topic feeds | sentiment regime, transient theme factor, macro defensiveness interactions |
| News-based alphas for cash equity portfolios | issuer news timestamps, sentiment, news volume | issuer news alpha, news volume surprise, news-conditioned reversal |

## 1.3 Lower Direct Alpha Value

| Source | Use Mainly For | Corporate Bond Translation |
|---|---|---|
| Protect, Diversify or Track Your Core | covariance estimation, regime-conditioned beta, correlation prediction | alpha conditioning variables, not standalone alphas |

---

## 2. Data Contract

## 2.1 Required RFQ Data

Each RFQ event should contain:

| Field | Symbol | Requirement | Notes |
|---|---:|---|---|
| RFQ timestamp | `t` | required | must be quote-time or request-time |
| Bond ID | `i` | required | ISIN or internal security ID |
| Side | `side_t` | required | dealer perspective |
| Size | `size_t` | required | notional or quantity |
| Venue | `venue_t` | preferred | MarketAxess, Tradeweb, Trumid, etc. |
| Protocol | `protocol_t` | preferred | list, single-name, firm, indicative |
| Quote | `Q_t` | optional for pure alpha | useful for markouts and aggressiveness |
| Fill flag | `fill_t` | optional for pure alpha | useful for selection analysis |

## 2.2 Required Market Data

| Field | Symbol | Requirement | Notes |
|---|---:|---|---|
| Bond fair value | `FV_{i,t}` | required | as-of fair value |
| Spread fair value | `S_{i,t}` | preferred | OAS, z-spread, G-spread, model spread |
| Spread duration | `D^S_i` | required for spread return | maps spread move into price return |
| Rate duration | `D^R_i` | preferred | rate hedge residualization |
| Issuer | `a(i)` | required | issuer curve features |
| Sector | `sector_i` | required | group flow and group curve features |
| Rating | `rating_i` | required | group construction |
| Maturity | `mat_i` | required | curve construction |
| Liquidity bucket | `liq_i` | preferred | conditioning and feature shrinkage |
| Issue size / ADV | `ADV_i` | preferred | scale size and liquidity |

## 2.3 Optional External Data

| Data | Use |
|---|---|
| CDX IG/HY | factor residuals and risk regime |
| Treasury yields / futures | rates-adjusted bond returns |
| LQD/HYG/JNK | ETF / cash-credit pressure |
| issuer equity | capital-structure lead-lag |
| VIX/MOVE | risk-appetite and volatility regimes |
| issuer news | issuer sentiment and news-volume conditioning |
| macro news sentiment | macro defensiveness and transient themes |

---

## 3. Canonical Targets

## 3.1 Price Fair-Value Return

If fair value is in clean price:

```text
R^P_{i,t,h} = FV^P_{i,t+h} - FV^P_{i,t}
```

Positive means the bond becomes richer in price.

## 3.2 Spread-Implied Return

If fair value is in spread:

```text
DeltaS_{i,t,h} = S_{i,t+h} - S_{i,t}
```

Approximate price return:

```text
R^S_{i,t,h} = -D^S_i * DeltaS_{i,t,h}
```

Positive means spread tightens and price richens.

## 3.3 Factor-Residual Return

Let:

```text
F_t = vector of public factor levels
DeltaF_{t,h} = F_{t+h} - F_t
beta_i = bond factor exposures
```

Then:

```text
R^{resid}_{i,t,h} = R^P_{i,t,h} - beta_i' DeltaF_{t,h}
```

Use this when you want alpha net of CDX, rates, ETF, and equity moves.

## 3.4 Recommended Horizons

Estimate all features against:

```text
h in {30m, 2h, 1d, 3d, 5d, 10d}
```

Interpretation by horizon:

| Horizon Shape | Interpretation |
|---|---|
| signal works only at 30m/2h | stale mark or microstructure alpha |
| signal strengthens into 1d/3d/5d | information or slow-flow alpha |
| signal initially works then reverses | liquidity-pressure alpha |
| signal works only at 10d | slow balance-sheet / factor repricing |

---

## 4. Sign Convention

Use dealer perspective for RFQ side:

```text
side_t = +1  means client sells bond to dealer
side_t = -1  means client buys bond from dealer
```

Client-seller pressure usually means:

```text
side_t = +1
```

If client selling is informed, expected future price return is negative:

```text
client seller pressure -> future price decline
```

Therefore, for alpha features based on sell pressure, define return-oriented signs so that:

```text
positive feature value -> positive expected future bond return
```

Example:

```text
FlowImbalance = P(client sells) - 0.5
FlowAlpha = -FlowImbalance
```

---

## 5. Leakage And As-Of Rules

Every feature must satisfy:

```text
feature_time <= prediction_time t
```

Rolling RFQ features must use:

```text
u < t
```

not:

```text
u <= t
```

unless the current RFQ information is genuinely available before prediction.

For return labels:

```text
label_time = t + h
```

Validation must be time-blocked:

```text
train period < validation period < test period
```

Use an embargo:

```text
embargo >= max forecast horizon
```

For 5-day alpha:

```text
embargo >= 5 trading days
```

---

## 6. Common Feature Objects

## 6.1 Buckets

Compute most features at several bucket levels:

```text
B in {
  ISIN,
  issuer,
  issuer x maturity bucket,
  sector,
  rating,
  sector x rating,
  sector x rating x maturity,
  venue,
  liquidity bucket,
  kNN neighbor set
}
```

Use hierarchical fallback:

```text
ISIN -> issuer -> sector/rating/maturity -> sector/rating -> global
```

## 6.2 Clocks

Use several clocks:

| Clock | Definition | Purpose |
|---|---|---|
| calendar | last fixed time window | active markets |
| event | last `N` RFQs | sparse bonds |
| notional | last fixed notional | block pressure |
| clock-of-day | local time bucket | clock seasonality |

Recommended windows:

```text
calendar W in {30m, 2h, 1d, 5d, 20d}
event N in {5, 10, 25, 50, 100, 250}
EWMA half-life tau in {30m, 2h, 1d, 5d}
```

---

# Alpha Family 1: Clock Seasonality Alpha

## 1.1 Source

Adapted from the intraday seasonality framework in **The Intraday Lab: Trading the Clock**.

## 1.2 Core Idea

Some returns are systematically biased by time of day, session, or market microstructure calendar.

For corporate bonds, the relevant clocks may include:

```text
NY open
London/NY overlap
CDX open
ETF open
ETF close
TRACE reporting windows
dealer balance-sheet/risk reduction periods
month-end
index rebalance dates
auction/new-issue windows
```

The hypothesis is:

```text
The same anonymous RFQ has different alpha content depending on when it arrives.
```

## 1.3 Required Inputs

```text
RFQ timestamp t
bond bucket B
future return R_{i,t,h}
clock bucket c(t)
```

## 1.4 Signal Formation

Define clock bucket:

```text
c(t) in {hour of day, half-hour of day, session bucket, event-clock bucket}
```

For each bucket `B`, clock bucket `c`, and horizon `h`, estimate in training data:

```text
mu_{B,c,h} = mean(R_{i,t,h} | i in B, c(t)=c)
```

Standard error:

```text
se_{B,c,h} = sd(R_{i,t,h} | i in B, c(t)=c) / sqrt(N_{B,c,h})
```

t-statistic:

```text
TClock_{B,c,h} = mu_{B,c,h} / se_{B,c,h}
```

Raw clock alpha:

```text
ClockAlphaRaw_{i,t,h} = TClock_{B,c(t),h}
```

Continuous normalized signal:

```text
ClockAlpha_{i,t,h}
= 2 * (ClockAlphaRaw - min_c ClockAlphaRaw)
     / (max_c ClockAlphaRaw - min_c ClockAlphaRaw)
   - 1
```

So:

```text
ClockAlpha in [-1,1]
```

Binary version:

```text
ClockAlphaBin =
  +1 if ClockAlpha > theta
  -1 if ClockAlpha < -theta
   0 otherwise
```

## 1.5 Smoothing

To avoid noisy clock buckets, use adjacent-bucket smoothing:

```text
TClockSmooth_{B,c,h}
= average of TClock over c-window around c
```

Use raw `TClock` only when statistically strong:

```text
TClockFinal =
  TClockRaw if |TClockRaw| > tau_T
  TClockSmooth otherwise
```

## 1.6 Hypotheses

Test:

```text
H1: Certain RFQ arrival clocks predict future FV returns.
H2: Clock alpha is stronger around liquidity transition times.
H3: Clock alpha interacts with flow imbalance and intensity.
```

## 1.7 Experiments

Single-feature test:

```text
R_{i,t,h}
= a + b ClockAlpha_{i,t,h} + controls + error
```

Interaction test:

```text
R_{i,t,h}
= a
  + b1 FlowAlpha_{i,t}
  + b2 ClockAlpha_{i,t,h}
  + b3 FlowAlpha_{i,t} * ClockAlpha_{i,t,h}
  + controls
  + error
```

## 1.8 Diagnostics

| Diagnostic | Requirement |
|---|---|
| bucket count | enough observations per clock bucket |
| stability | same sign across train/test |
| multiple testing | adjust clock-bucket discoveries |
| horizon curve | not only one accidental horizon |
| venue split | robust by venue |

## 1.9 Failure Modes

| Failure | Interpretation |
|---|---|
| alpha only in-sample | clock overfit |
| alpha disappears after date FE | broad market calendar effect |
| alpha only around stale marks | mark-timing artifact |
| alpha too sparse | bucket hierarchy too granular |

---

# Alpha Family 2: Triplet Momentum/Reversal Alpha

## 2.1 Source

Adapted from **The Intraday Lab: Catching the Beat**.

## 2.2 Core Idea

A return pattern requires three points:

```text
p1 -> p2 -> p3
```

The first move is the lagged move:

```text
L = p2 - p1
```

The second move is the future move:

```text
H = p3 - p2
```

If the signs agree, the pattern is momentum. If signs differ, it is reversal.

Corporate bond translation:

```text
Does a past FV/spread/factor-residual move observed at a specific vantage time predict continuation or reversal over a future horizon?
```

## 2.3 Required Inputs

```text
FV_{i,t}
S_{i,t}
factor residual return
clock bucket v(t)
bucket B
```

## 2.4 Triplet Definition

Define triplet:

```text
theta = (l, v, h)
```

where:

```text
l = lag length
v = vantage clock bucket
h = forecast horizon
```

At prediction time `t` with `v(t)=v`:

```text
PastMove_{i,t,l} = FV_{i,t} - FV_{i,t-l}
FutureMove_{i,t,h} = FV_{i,t+h} - FV_{i,t}
```

For spread:

```text
PastSpreadReturn_{i,t,l} = -D^S_i * (S_{i,t} - S_{i,t-l})
FutureSpreadReturn_{i,t,h} = -D^S_i * (S_{i,t+h} - S_{i,t})
```

## 2.5 Pattern Estimation

For each `B`, `v`, `l`, `h`, estimate:

```text
rho_{B,v,l,h}
= SpearmanCorr(PastMove_{i,t,l}, FutureMove_{i,t,h})
```

Use Spearman rather than Pearson because:

```text
it is rank-based,
less sensitive to outliers,
does not assume linearity,
works better across heterogeneous bonds.
```

## 2.6 Signal Formation

Raw signal:

```text
TripletAlphaRaw_{i,t,l,h}
= rho_{B,v,l,h} * rank_z(PastMove_{i,t,l})
```

Momentum case:

```text
rho > 0 => positive past move predicts positive future move
```

Reversal case:

```text
rho < 0 => positive past move predicts negative future move
```

Binary pattern classifier:

```text
Pattern_{B,v,l,h}
= momentum if rho > 0 and p_adj < alpha
= reversal if rho < 0 and p_adj < alpha
= none otherwise
```

Final signal:

```text
TripletAlpha_{i,t}
= weighted average over selected theta of TripletAlphaRaw_{i,t,theta}
```

Weights:

```text
w_theta ∝ |rho_theta| / vol_error_theta
```

or simply:

```text
equal weight across top K validated triplets
```

## 2.7 Hypotheses

```text
H1: Some bond buckets have predictable momentum/reversal pockets.
H2: Reversal dominates after liquidity shocks or stale-mark jumps.
H3: Momentum dominates after public factor confirmation.
H4: Triplet patterns are stronger for factor-residual returns than raw returns.
```

## 2.8 Experiments

Base regression:

```text
R_{i,t,h}
= a + b TripletAlpha_{i,t} + controls + error
```

Residual return test:

```text
R^{resid}_{i,t,h}
= a + b TripletAlpha^{resid}_{i,t} + controls + error
```

Regime interaction:

```text
R_{i,t,h}
= a
  + b1 TripletAlpha
  + b2 LiquidityStress
  + b3 TripletAlpha * LiquidityStress
  + controls
  + error
```

## 2.9 Diagnostics

| Diagnostic | Requirement |
|---|---|
| multiple testing | false discovery control across many `l,v,h` |
| cluster stability | significant regions should cluster, not be isolated dots |
| OOS persistence | top triplets survive later periods |
| sign stability | momentum/reversal classification stable |
| horizon consistency | economically plausible decay |

## 2.10 Failure Modes

| Failure | Interpretation |
|---|---|
| many isolated significant triplets | data mining |
| signal works only in raw price but not residual | public factor effect |
| signal requires too many parameters | overfit |
| signal flips sign frequently | unstable market microstructure |

---

# Alpha Family 3: Variance-Ratio Reversal Alpha

## 3.1 Source

Adapted from **Gearing into Reverse**.

## 3.2 Core Idea

Variance ratios measure whether prices behave more like:

```text
random walk,
momentum process,
mean-reverting process.
```

For a random walk:

```text
Var(k-period return) ≈ k * Var(1-period return)
```

So:

```text
VR(k) ≈ 1
```

If:

```text
VR(k) < 1
```

returns are mean-reverting.

If:

```text
VR(k) > 1
```

returns are trending.

## 3.3 Required Inputs

```text
FV return series
spread return series
factor-residual return series
bucket B
rolling window W
horizon k
```

## 3.4 Formula

One-period return:

```text
r_{i,t} = FV_{i,t} - FV_{i,t-1}
```

k-period return:

```text
r^{(k)}_{i,t} = FV_{i,t} - FV_{i,t-k}
```

Variance ratio:

```text
VR_{i,t,k,W}
= Var_W(r^{(k)}_{i,t}) / [k * Var_W(r_{i,t})]
```

Use residual returns as preferred:

```text
r^{resid}_{i,t} = r_{i,t} - beta_i' DeltaF_t
```

## 3.5 Signal Formation

Recent return:

```text
RecentReturn_{i,t,L} = FV_{i,t} - FV_{i,t-L}
```

Reversal indicator:

```text
MeanRevertingState_{i,t}
= 1{VR_{i,t,k,W} < theta_VR}
```

Return alpha:

```text
VRReversalAlpha_{i,t}
= -rank_z(RecentReturn_{i,t,L}) * MeanRevertingState_{i,t}
```

Momentum alternative:

```text
VRMomentumAlpha_{i,t}
= rank_z(RecentReturn_{i,t,L}) * 1{VR_{i,t,k,W} > theta_M}
```

## 3.6 Hypotheses

```text
H1: Low variance ratio predicts future reversal in bond FV residuals.
H2: Variance-ratio reversal is stronger in low-volatility states.
H3: Variance-ratio reversal is weaker when public factors confirm the move.
```

## 3.7 Experiments

```text
R_{i,t,h}
= a
  + b1 VRReversalAlpha_{i,t}
  + b2 VRMomentumAlpha_{i,t}
  + controls
  + error
```

Conditioned version:

```text
R_{i,t,h}
= a
  + b1 VRReversalAlpha
  + b2 VRReversalAlpha * LowVolState
  + b3 VRReversalAlpha * FactorConfirm
  + controls
  + error
```

## 3.8 Diagnostics

| Diagnostic | Requirement |
|---|---|
| VR stability | not dominated by one jump |
| residual version | works after factor adjustment |
| liquidity split | not only stale illiquid marks |
| horizon profile | reversal should decay over plausible horizon |

---

# Alpha Family 4: Low-Volatility Reversal Alpha

## 4.1 Source

Adapted from the finding that intraday reversal was stronger in lower volatility / lower risk-appetite sensitivity environments.

## 4.2 Core Idea

When volatility is low, price moves may be more likely to represent temporary liquidity pressure rather than new information.

So:

```text
low volatility + large recent move -> reversal candidate
```

## 4.3 Inputs

```text
RecentReturn_{i,t,L}
RealizedVol_{i,t,W}
WidthZ_{i,t}
RiskAppetiteBeta_{i,t}
```

## 4.4 Formula

Rolling realized volatility:

```text
Vol_{i,t,W} = sd(r_{i,u}, u in [t-W,t))
```

Vol z-score:

```text
VolZ_{i,t}
= (Vol_{i,t,W} - median(Vol_{i})) / mad(Vol_i)
```

Low-vol state:

```text
LowVolState_{i,t}
= 1{VolZ_{i,t} < q_{low}}
```

Signal:

```text
LowVolReversalAlpha_{i,t}
= -rank_z(RecentReturn_{i,t,L}) * LowVolState_{i,t}
```

## 4.5 Hypotheses

```text
H1: Reversal is stronger when volatility is low.
H2: Reversal is weaker during credit stress.
H3: Low-vol reversal is strongest for factor-residual moves.
```

## 4.6 Experiments

```text
R_{i,t,h}
= a
  + b1 RecentReturn_{i,t,L}
  + b2 LowVolReversalAlpha_{i,t}
  + controls
  + error
```

Pass:

```text
b2 > 0
```

because positive alpha should predict positive future return.

---

# Alpha Family 5: Risk-Appetite-Conditioned Reversal Alpha

## 5.1 Source

Adapted from the reversal paper's conditioning on correlation to global risk appetite.

## 5.2 Core Idea

Some instruments are mainly macro/risk proxies. Moves in those instruments are more likely to continue if they reflect risk appetite.

Other instruments are less tied to broad risk appetite. Their moves are more likely to reverse when driven by local flow or liquidity.

## 5.3 Inputs

```text
bond returns
VIX/MOVE/CDX returns
ETF returns
recent return
variance ratio
```

## 5.4 Formula

Risk-appetite proxy:

```text
RA_t = first PC of [VIX, MOVE, CDX_HY, HYG, SPX]
```

or simpler:

```text
RA_t = -SPX_return + CDX_HY_spread_change + VIX_change
```

Rolling beta:

```text
beta^{RA}_{i,t}
= Cov_W(r_{i}, RA) / Var_W(RA)
```

Risk-appetite correlation:

```text
corr^{RA}_{i,t}
= Corr_W(r_i, RA)
```

Low risk-appetite-sensitivity state:

```text
LowRASensitivity_{i,t}
= 1{|corr^{RA}_{i,t}| < threshold}
```

Signal:

```text
RAConditionedReversalAlpha_{i,t}
= -rank_z(RecentReturn_{i,t,L})
   * 1{VR_{i,t}<theta}
   * LowRASensitivity_{i,t}
```

## 5.5 Hypotheses

```text
H1: Reversal works better when bond returns are less tied to broad risk appetite.
H2: When risk-appetite beta is high, continuation or factor-following dominates.
```

## 5.6 Experiments

```text
R_{i,t,h}
= a
  + b1 VRReversalAlpha
  + b2 RAConditionedReversalAlpha
  + b3 CrossAssetLead
  + controls
  + error
```

---

# Alpha Family 6: Curve PCA Momentum Alpha

## 6.1 Source

Adapted from **Speeding Into The Curve**.

## 6.2 Core Idea

Issuer curves and sector/rating curves have latent level, slope, and curvature factors.

The movement of those latent factors may exhibit momentum or reversal. The residual after removing the main curve PCs may also contain alpha.

Corporate bond translation:

```text
For each issuer or group curve, decompose cross-maturity returns into PC1/PC2/PC3 and residuals.
Use recent PC or residual movement to predict future bond returns.
```

## 6.3 Inputs

```text
bond FV returns by issuer or group
maturity buckets
spread duration
liquidity filters
rolling window W_PCA
```

## 6.4 Curve Construction

For issuer `a`, create return vector across bonds:

```text
R_{a,t} = [r_{i1,t}, r_{i2,t}, ..., r_{in,t}]'
```

where all bonds belong to issuer `a`.

If issuer is too sparse, use:

```text
sector x rating x maturity group
```

Standardize by rolling volatility:

```text
Rtilde_{a,t,j} = R_{a,t,j} / sigma_{a,j,t}
```

Run rolling PCA over window `W_PCA`:

```text
Rtilde_{a,t} ≈ L_{a,t} f_{a,t}
```

where:

```text
f1 = level
f2 = slope
f3 = curvature
```

## 6.5 PC Momentum Features

For PC `m`:

```text
PCMomentum_{a,m,t,L}
= sum_{u=t-L}^{t-1} f_{a,m,u}
```

Return-oriented bond alpha:

```text
CurvePCMomentumAlpha_{i,t}
= exposure_{i,m,t} * PCMomentum_{a,m,t,L}
```

where:

```text
exposure_{i,m,t} = loading of bond i on PC m
```

## 6.6 Hypotheses

```text
H1: issuer/group level PC momentum predicts future returns.
H2: slope PC momentum predicts maturity-specific returns.
H3: curvature PC momentum predicts belly/wing relative returns.
```

## 6.7 Experiments

```text
R_{i,t,h}
= a
  + b1 CurvePC1MomentumAlpha_{i,t}
  + b2 CurvePC2MomentumAlpha_{i,t}
  + b3 CurvePC3MomentumAlpha_{i,t}
  + controls
  + error
```

Run separately for:

```text
issuer curves
sector/rating curves
liquidity-filtered curves
```

## 6.8 Diagnostics

| Diagnostic | Requirement |
|---|---|
| curve coverage | enough bonds per issuer/group |
| PCA stability | loadings not erratic |
| economic interpretation | PC1 level, PC2 slope, PC3 curvature |
| residual robustness | signal survives excluding illiquid marks |

---

# Alpha Family 7: Curve-To-Level Spillover Alpha

## 7.1 Source

Adapted from the curve spillover idea in **Speeding Into The Curve**.

## 7.2 Core Idea

Recent slope or curve movement can predict future level movement.

Corporate bond translation:

```text
If the issuer curve steepens because long bonds sell off first,
the issuer level may later cheapen.
```

or:

```text
If short bonds lead a curve move, long bonds may catch up.
```

## 7.3 Inputs

```text
issuer/group PC1 score
issuer/group PC2 score
issuer/group PC3 score
future issuer level return
```

## 7.4 Signal Formation

Recent slope movement:

```text
PC2Mom_{a,t,L} = sum_{u=t-L}^{t-1} f_{a,2,u}
```

Future level return:

```text
FutureLevelReturn_{a,t,h} = f_{a,1,t+h} - f_{a,1,t}
```

Estimate training relationship:

```text
FutureLevelReturn_{a,t,h}
= alpha + beta_spill PC2Mom_{a,t,L} + error
```

Spillover alpha:

```text
CurveToLevelSpilloverAlpha_{i,t}
= loading_{i,1,t} * beta_spill * PC2Mom_{a,t,L}
```

## 7.5 Hypotheses

```text
H1: slope pressure leads issuer-level repricing.
H2: curve-to-level spillover is stronger during flow imbalance.
H3: curve-to-level spillover is stronger in illiquid bonds.
```

## 7.6 Experiments

```text
R_{i,t,h}
= a
  + b1 CurveToLevelSpilloverAlpha_{i,t}
  + b2 FlowAlpha_{issuer,t}
  + b3 CurveToLevelSpilloverAlpha_{i,t} * FlowAlpha_{issuer,t}
  + controls
  + error
```

---

# Alpha Family 8: Bond Curve Residual Alpha

## 8.1 Source

Adapted from the residual-momentum and curve decomposition framework.

## 8.2 Core Idea

After explaining a bond return by issuer or group curve PCs, the residual may mean-revert or continue.

This is very close to corporate bond relative value.

## 8.3 Inputs

```text
bond FV return
issuer/group PC returns
rolling residual
residual volatility
```

## 8.4 Formula

Fit:

```text
r_{i,t}
= beta_{i,1} f_{a,1,t}
 + beta_{i,2} f_{a,2,t}
 + beta_{i,3} f_{a,3,t}
 + e_{i,t}
```

Residual z-score:

```text
CurveResidualZ_{i,t}
= (e_{i,t} - mean_W(e_i)) / sd_W(e_i)
```

Mean-reversion alpha:

```text
CurveResidualReversalAlpha_{i,t}
= -CurveResidualZ_{i,t}
```

Residual momentum alpha:

```text
CurveResidualMomentumAlpha_{i,t}
= sum_{u=t-L}^{t-1} e_{i,u} / sd_W(e_i)
```

## 8.5 Hypotheses

```text
H1: curve residuals mean-revert in liquid bonds.
H2: curve residuals continue in stressed or informed-flow states.
H3: residual momentum is stronger when confirmed by issuer RFQ flow.
```

## 8.6 Experiments

```text
R_{i,t,h}
= a
  + b1 CurveResidualReversalAlpha
  + b2 CurveResidualMomentumAlpha
  + b3 FlowAlpha
  + b4 CurveResidualReversalAlpha * FlowAlpha
  + controls
  + error
```

---

# Alpha Family 9: PC Residual Momentum Alpha

## 9.1 Source

Adapted from PC residual momentum in **Speeding Into The Curve**.

## 9.2 Core Idea

Instead of using raw momentum, remove dominant curve factors and accumulate unexplained residual returns.

This isolates idiosyncratic or higher-order curve movement.

## 9.3 Formula

PC-attributed return:

```text
r^{PC123}_{i,t}
= beta_{i,1} f_{1,t}
 + beta_{i,2} f_{2,t}
 + beta_{i,3} f_{3,t}
```

Residual:

```text
r^{resPC}_{i,t} = r_{i,t} - r^{PC123}_{i,t}
```

Residual momentum:

```text
PCResidualMomentum_{i,t,L}
= product_{u=t-L}^{t-1} (1 + r^{resPC}_{i,u}) - 1
```

or additive:

```text
PCResidualMomentum_{i,t,L}
= sum_{u=t-L}^{t-1} r^{resPC}_{i,u}
```

Alpha:

```text
PCResidualMomentumAlpha_{i,t}
= zscore(PCResidualMomentum_{i,t,L})
```

## 9.4 Hypotheses

```text
H1: residual momentum captures slow diffusion within issuer/group curves.
H2: residual momentum is stronger in illiquid bonds.
H3: residual momentum decays faster when public factor confirmation is absent.
```

## 9.5 Experiments

```text
R^{resid}_{i,t,h}
= a
  + b PCResidualMomentumAlpha_{i,t}
  + controls
  + error
```

---

# Alpha Family 10: Roll-Down / Carry-Adjusted Curve Alpha

## 10.1 Source

Inspired by the curve roll-down discussion in **Speeding Into The Curve**.

## 10.2 Core Idea

Part of expected bond return is predictable from carry and roll-down. For alpha prediction, we want to separate:

```text
structural carry/roll
from unexpected flow or RV alpha.
```

## 10.3 Inputs

```text
bond curve
spread curve
maturity
duration
carry
roll-down estimate
```

## 10.4 Formula

Expected carry/roll return:

```text
CarryRoll_{i,t,h}
= Carry_{i,t,h} + RollDown_{i,t,h}
```

Unexpected return target:

```text
R^{exCarry}_{i,t,h}
= R_{i,t,h} - CarryRoll_{i,t,h}
```

Carry-adjusted RV alpha:

```text
CarryAdjustedRVAlpha_{i,t}
= RVAlpha_{i,t} - CarryRoll_{i,t,h}
```

## 10.5 Hypotheses

```text
H1: raw flow alpha predicts returns beyond carry/roll.
H2: curve residual alpha is stronger after carry/roll adjustment.
H3: long/short maturity flow partly proxies roll-down attractiveness.
```

## 10.6 Experiments

```text
R^{exCarry}_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 CurveResidualAlpha
  + b3 CarryAdjustedRVAlpha
  + controls
  + error
```

---

# Alpha Family 11: Issuer News Sentiment Alpha

## 11.1 Source

Adapted from **News-based alphas for cash equity portfolios**.

## 11.2 Core Idea

News sentiment can predict asset returns, but the standalone signal often decays quickly and can be costly. In corporate bonds, the more plausible use is:

```text
issuer-specific news sentiment as a slow or event-conditioned credit signal.
```

## 11.3 Required Inputs

```text
issuer news timestamp
issuer mapping
news sentiment score
news category/topic
news novelty/staleness flag if available
```

## 11.4 Signal Formation

Issuer sentiment over lookback `L`:

```text
NewsSent_{a,t,L}
= sum_{news n for issuer a, t-L <= time_n < t} sentiment_n
```

News-count normalized sentiment:

```text
AvgNewsSent_{a,t,L}
= sum sentiment_n / number_of_news_n
```

Market-adjusted sentiment:

```text
IdioNewsSent_{a,t,L}
= NewsSent_{a,t,L} - MarketNewsSent_{t,L}
```

where:

```text
MarketNewsSent_{t,L}
= average news sentiment across all issuers in universe
```

Alpha:

```text
IssuerNewsSentimentAlpha_{i,t}
= zscore(IdioNewsSent_{a(i),t,L})
```

## 11.5 Hypotheses

```text
H1: negative issuer news sentiment predicts spread widening.
H2: issuer news sentiment works better around event windows.
H3: news sentiment improves flow alpha by distinguishing informed selling from liquidity selling.
```

## 11.6 Experiments

```text
R_{i,t,h}
= a
  + b1 IssuerNewsSentimentAlpha
  + b2 FlowAlpha
  + b3 IssuerNewsSentimentAlpha * FlowAlpha
  + controls
  + error
```

## 11.7 Failure Modes

| Failure | Interpretation |
|---|---|
| works only at very short horizon | latency-sensitive news alpha |
| disappears after equity/CDX controls | public factor reaction |
| only works for large issuers | coverage bias |
| unstable by provider | data-vendor dependence |

---

# Alpha Family 12: News Volume Conditioning Alpha

## 12.1 Source

Adapted from the news-volume/reversion interaction in **News-based alphas for cash equity portfolios**.

## 12.2 Core Idea

News volume may not predict return sign by itself. It can predict the **strength or reliability** of another alpha.

In the source logic:

```text
reversion is stronger when there is less news,
because low news volume implies slower information diffusion or less fundamental confirmation.
```

Corporate bond translation:

```text
If a bond looks cheap/rich with low issuer news volume, mean reversion may be stronger.
If there is high issuer news volume, the move may be fundamental and less likely to reverse.
```

## 12.3 Formula

News volume:

```text
NewsCount_{a,t,L}
= number of issuer news items in [t-L,t)
```

Historical normalized:

```text
NewsVolumeZ_{a,t,L}
= (NewsCount_{a,t,L} - mean_W(NewsCount_a)) / sd_W(NewsCount_a)
```

Low-news indicator:

```text
LowNews_{a,t}
= 1{NewsVolumeZ_{a,t,L} < q_low}
```

News-conditioned RV reversal:

```text
NewsConditionedRVAlpha_{i,t}
= RVAlpha_{i,t} * LowNews_{a,t}
```

News-conditioned flow reversal:

```text
NewsConditionedFlowReversalAlpha_{i,t}
= FlowReversalAlpha_{i,t} * LowNews_{a,t}
```

## 12.4 Hypotheses

```text
H1: RV reversion is stronger when issuer news volume is low.
H2: Flow imbalance is more likely informational when news volume is high.
H3: Flow imbalance is more likely liquidity pressure when news volume is low.
```

## 12.5 Experiments

```text
R_{i,t,h}
= a
  + b1 RVAlpha
  + b2 NewsVolumeZ
  + b3 RVAlpha * LowNews
  + b4 FlowAlpha * NewsVolumeZ
  + controls
  + error
```

---

# Alpha Family 13: Macro Sentiment Regime Interaction

## 13.1 Source

Adapted from **Catching the sentiment waves**.

## 13.2 Core Idea

Sentiment may be more useful as a regime classifier than as a direct signal.

Corporate bond alpha features should be conditioned on:

```text
growth sentiment
inflation sentiment
rates sentiment
credit sentiment
risk sentiment
```

## 13.3 Inputs

```text
macro sentiment scores by topic
public risk indicators
credit/rates factors
```

## 13.4 Regime Formation

Let:

```text
Sent_t = [GrowthSent_t, InflationSent_t, RatesSent_t, CreditSent_t, RiskSent_t]
```

Define regimes by quantiles:

```text
HighRiskSent_t = 1{RiskSent_t > q_70}
LowRiskSent_t = 1{RiskSent_t < q_30}
```

Or by HMM:

```text
Regime_t in {risk_on, neutral, risk_off}
```

## 13.5 Signal Formation

Regime-conditioned flow:

```text
SentRegimeFlowAlpha_{i,t}
= FlowAlpha_{i,t} * HighRiskSent_t
```

Regime-conditioned RV:

```text
SentRegimeRVAlpha_{i,t}
= RVAlpha_{i,t} * LowRiskSent_t
```

Regime-conditioned cross-asset lead:

```text
SentRegimeCrossAssetAlpha_{i,t}
= CrossAssetLead_{i,t} * HighRiskSent_t
```

## 13.6 Hypotheses

```text
H1: Flow alpha is more informational in risk-off sentiment regimes.
H2: RV reversion is stronger in low-risk regimes.
H3: Cross-asset lead-lag is stronger when macro sentiment is shifting quickly.
```

## 13.7 Experiments

```text
R_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 RiskSentRegime
  + b3 FlowAlpha * RiskSentRegime
  + b4 RVAlpha * LowRiskSentRegime
  + controls
  + error
```

---

# Alpha Family 14: Transient Theme Factor Alpha

## 14.1 Source

Adapted from the transient risk factor idea in **Catching the sentiment waves**.

## 14.2 Core Idea

Market themes change. A fixed factor model may miss temporary drivers such as:

```text
regional banks
AI capex
oil shock
commercial real estate
inflation scare
refinancing wall
rating migration
China growth
```

A transient theme factor captures what the market is currently discussing or repricing.

## 14.3 Inputs

```text
topic-level news counts
topic-level sentiment
issuer-to-topic exposure
sector-to-topic exposure
```

## 14.4 Theme Score

For topic `m`:

```text
ThemeIntensity_{m,t}
= zscore(news_count_{m,t,L})
```

```text
ThemeSentiment_{m,t}
= average sentiment for topic m over [t-L,t)
```

Theme factor:

```text
ThemeFactor_{m,t}
= ThemeIntensity_{m,t} * ThemeSentiment_{m,t}
```

Issuer exposure:

```text
ThemeExposure_{i,m}
= exposure of issuer/bond i to topic m
```

Transient theme alpha:

```text
TransientThemeAlpha_{i,t}
= sum_m ThemeExposure_{i,m} * ThemeFactor_{m,t}
```

## 14.5 Hypotheses

```text
H1: theme-exposed bonds react with a delay to transient themes.
H2: flow alpha is stronger when it aligns with a live theme.
H3: RV dislocations are less likely to mean-revert when explained by a live theme.
```

## 14.6 Experiments

```text
R_{i,t,h}
= a
  + b1 TransientThemeAlpha
  + b2 FlowAlpha
  + b3 TransientThemeAlpha * FlowAlpha
  + b4 RVAlpha
  + b5 TransientThemeAlpha * RVAlpha
  + controls
  + error
```

---

# Alpha Family 15: Covariance-Regime-Conditioned Alpha

## 15.1 Source

Adapted from **Protect, Diversify or Track Your Core**.

## 15.2 Core Idea

This paper is not mainly a return-alpha source. Its useful transfer is:

```text
alpha strength changes when covariance, beta, and correlation regimes change.
```

In stressed regimes, bonds become more correlated and idiosyncratic alphas may be overwhelmed by systematic factors.

## 15.3 Inputs

```text
rolling bond-factor betas
rolling correlation matrix
cross-sectional average correlation
CDX/rates/ETF factor returns
volatility state
```

## 15.4 Features

Average correlation:

```text
AvgCorr_t
= average_{i<j} Corr_W(r_i,r_j)
```

Correlation shock:

```text
CorrShock_t
= AvgCorr_t - median_W(AvgCorr)
```

Beta instability:

```text
BetaInstability_{i,t}
= ||beta_{i,t} - beta_{i,t-W}||
```

High-correlation regime:

```text
HighCorrRegime_t
= 1{AvgCorr_t > q_80}
```

## 15.5 Signal Formation

Conditioned flow:

```text
CorrConditionedFlowAlpha_{i,t}
= FlowAlpha_{i,t} * HighCorrRegime_t
```

Conditioned RV:

```text
CorrConditionedRVAlpha_{i,t}
= RVAlpha_{i,t} * (1 - HighCorrRegime_t)
```

Conditioned neighbor flow:

```text
CorrConditionedNeighborAlpha_{i,t}
= NeighborFlowAlpha_{i,t} * HighCorrRegime_t
```

## 15.6 Hypotheses

```text
H1: Neighbor and group flow matter more in high-correlation regimes.
H2: idiosyncratic RV mean reversion matters more in low-correlation regimes.
H3: cross-asset lead-lag matters more when beta instability is high.
```

## 15.7 Experiments

```text
R_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 NeighborFlowAlpha
  + b3 RVAlpha
  + b4 FlowAlpha * HighCorrRegime
  + b5 NeighborFlowAlpha * HighCorrRegime
  + b6 RVAlpha * LowCorrRegime
  + controls
  + error
```

---

# Alpha Family 16: Flow-Confirmed Triplet Alpha

## 16.1 Source Combination

Combines:

```text
Triplet momentum/reversal
anonymous RFQ flow imbalance
```

## 16.2 Core Idea

Triplet price patterns are more believable when anonymous RFQ flow confirms the direction.

## 16.3 Formula

Triplet alpha:

```text
TripletAlpha_{i,t}
```

Flow alpha:

```text
FlowAlpha_{i,t}
```

Agreement:

```text
TripletFlowAgree_{i,t}
= 1{sign(TripletAlpha_{i,t}) = sign(FlowAlpha_{i,t})}
```

Continuous confirmation:

```text
FlowConfirmedTripletAlpha_{i,t}
= TripletAlpha_{i,t} * FlowAlpha_{i,t}
```

Alternative:

```text
TripletAlphaConfirmed_{i,t}
= TripletAlpha_{i,t} * 1{TripletFlowAgree_{i,t}=1}
```

## 16.4 Hypotheses

```text
H1: price-pattern alpha is stronger when RFQ flow confirms it.
H2: price-pattern reversal is stronger when flow exhaustion confirms it.
H3: price-pattern momentum is stronger when issuer/group flow confirms it.
```

## 16.5 Experiments

```text
R_{i,t,h}
= a
  + b1 TripletAlpha
  + b2 FlowAlpha
  + b3 FlowConfirmedTripletAlpha
  + controls
  + error
```

---

# Alpha Family 17: Clock-Conditioned Flow Alpha

## 17.1 Source Combination

Combines:

```text
clock seasonality
anonymous RFQ flow
```

## 17.2 Core Idea

Flow may be more informative at certain times.

Examples:

```text
early NY session flow may contain fresh information
late-day flow may reflect liquidity/risk reduction
month-end flow may reflect benchmark activity
ETF close flow may reflect portfolio hedging
```

## 17.3 Formula

```text
ClockConditionedFlowAlpha_{i,t}
= FlowAlpha_{i,t} * ClockAlpha_{B,c(t),h}
```

Session-specific version:

```text
FlowAlpha_NYOpen = FlowAlpha * 1{clock in NY open window}
FlowAlpha_Close = FlowAlpha * 1{clock in close window}
```

## 17.4 Hypotheses

```text
H1: seller pressure near close is more liquidity-driven and mean-reverting.
H2: seller pressure after news/open is more informational and continues.
H3: flow in London/NY overlap has higher price-discovery content.
```

## 17.5 Experiments

```text
R_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 ClockAlpha
  + b3 ClockConditionedFlowAlpha
  + controls
  + error
```

---

# Alpha Family 18: Curve-Conditioned Flow Alpha

## 18.1 Source Combination

Combines:

```text
curve spillover
anonymous RFQ flow
```

## 18.2 Core Idea

Flow is more meaningful when it agrees with curve deformation.

Example:

```text
long-end issuer selling + issuer curve steepening
=> stronger negative alpha for long bonds
```

## 18.3 Formula

Issuer curve pressure:

```text
CurvePressure_{a,t} = LongImb_{a,t} - ShortImb_{a,t}
```

Maturity sign:

```text
maturity_sign_i =
  +1 for long bond
   0 for belly bond
  -1 for short bond
```

Curve flow alpha:

```text
CurveFlowAlpha_{i,t}
= -maturity_sign_i * CurvePressure_{a,t}
```

Curve-confirmed own flow:

```text
CurveConfirmedFlowAlpha_{i,t}
= FlowAlpha_{i,t} * CurveFlowAlpha_{i,t}
```

## 18.4 Hypotheses

```text
H1: own-bond flow predicts returns better when issuer curve flow confirms it.
H2: curve flow identifies whether the alpha is level, slope, or local RV.
```

## 18.5 Experiments

```text
R_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 CurveFlowAlpha
  + b3 CurveConfirmedFlowAlpha
  + controls
  + error
```

---

# Alpha Family 19: Public-Factor-Confirmed Flow Alpha

## 19.1 Source Combination

Combines:

```text
cross-asset lead-lag
news/sentiment confirmation
flow alpha
```

## 19.2 Core Idea

Anonymous RFQ flow is more likely to be informational when public liquid instruments are moving in the same direction.

## 19.3 Formula

Public factor lead:

```text
CrossAssetLead_{i,t}
= beta_i' DeltaF_t
```

Flow alpha:

```text
FlowAlpha_{i,t}
```

Confirmation:

```text
FactorFlowAgree_{i,t}
= 1{sign(CrossAssetLead_{i,t}) = sign(FlowAlpha_{i,t})}
```

Continuous:

```text
FactorConfirmedFlowAlpha_{i,t}
= FlowAlpha_{i,t} * CrossAssetLead_{i,t}
```

## 19.4 Hypotheses

```text
H1: flow plus factor confirmation predicts continuation.
H2: flow without factor confirmation is more likely liquidity pressure.
H3: factor-confirmed flow works faster than pure RFQ flow.
```

## 19.5 Experiments

```text
R_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 CrossAssetLead
  + b3 FactorConfirmedFlowAlpha
  + controls
  + error
```

---

# Alpha Family 20: Flow Exhaustion / Reversal Alpha

## 20.1 Source Combination

Combines:

```text
RFQ flow imbalance
reversal mechanics
news-volume conditioning
liquidity pressure
```

## 20.2 Core Idea

Extreme one-sided flow can be either:

```text
informed continuation
```

or:

```text
liquidity pressure that reverses after exhaustion.
```

The exhaustion signal tries to identify the second case.

## 20.3 Formula

Short-window imbalance:

```text
ImbShort_{B,t}
```

Long-window imbalance:

```text
ImbLong_{B,t}
```

Acceleration:

```text
FlowAcceleration_{B,t}
= ImbShort_{B,t} - ImbLong_{B,t}
```

Extreme pressure:

```text
ExtremeFlow_{B,t}
= 1{|ImbLong_{B,t}| > q_90(|ImbLong_B|)}
```

Exhaustion:

```text
FlowExhaustion_{B,t}
= ExtremeFlow_{B,t}
  * [-sign(ImbLong_{B,t}) * FlowAcceleration_{B,t}]
```

Return alpha:

```text
FlowExhaustionReversalAlpha_{B,t}
= sign(ImbLong_{B,t}) * FlowExhaustion_{B,t}
```

Interpretation:

```text
extreme client selling that fades -> positive reversal alpha
extreme client buying that fades -> negative reversal alpha
```

## 20.4 Hypotheses

```text
H1: exhaustion predicts reversal when news volume is low.
H2: exhaustion predicts reversal when public factors do not confirm the move.
H3: exhaustion predicts continuation when news volume and public factors confirm the move.
```

## 20.5 Experiments

```text
R_{i,t,h}
= a
  + b1 FlowAlpha
  + b2 FlowExhaustionReversalAlpha
  + b3 FlowExhaustionReversalAlpha * LowNews
  + b4 FlowExhaustionReversalAlpha * FactorConfirm
  + controls
  + error
```

---

## 21. Master Experiment Plan

## 21.1 Stage 1: Single Alpha Screening

For each feature `X`:

```text
R_{i,t,h} = a + b X_{i,t} + controls + error
```

Record:

```text
coverage
mean
standard deviation
coefficient
t-stat
OOS R2
rank IC
top-bottom decile return
horizon curve
```

## 21.2 Stage 2: Nested Model Families

Model ladder:

```text
M0: controls only
M1: M0 + flow alphas
M2: M1 + clock and triplet alphas
M3: M2 + reversal / VR alphas
M4: M3 + curve PCA / residual alphas
M5: M4 + sentiment / news interactions
M6: M5 + covariance regime interactions
```

## 21.3 Stage 3: Continuation Versus Reversal Classification

For each alpha, estimate horizon curve:

```text
beta(h), IC(h), decile_spread(h)
```

Classify:

| Pattern | Classification |
|---|---|
| same sign and growing to 3-5d | information alpha |
| same sign only intraday | stale-mark alpha |
| sign reversal after short horizon | liquidity-pressure reversal |
| no stable sign | reject |

## 21.4 Stage 4: Robustness Splits

Run all tests by:

```text
IG / HY
liquid / illiquid
large / small RFQ
single-name / list RFQ
venue
sector
rating bucket
maturity bucket
calm / stressed market
event / non-event
high / low correlation regime
high / low news volume
```

## 21.5 Stage 5: Promotion Criteria

Promote a feature only if:

```text
1. It is computable as-of.
2. It has sufficient coverage.
3. It improves OOS rank IC or OOS R2.
4. It has stable sign across time.
5. It survives at least three major universe splits.
6. It is not explained away by public factors unless it is explicitly a factor lead.
7. Its horizon shape has an economic interpretation.
```

---

## 22. Prioritized Implementation List

## 22.1 Implement First

These do not require news data:

```text
1. ClockAlpha
2. TripletMomentumReversalAlpha
3. VarianceRatioReversalAlpha
4. LowVolReversalAlpha
5. RiskAppetiteConditionedReversalAlpha
6. CurvePCMomentumAlpha
7. CurveToLevelSpilloverAlpha
8. BondCurveResidualAlpha
9. PCResidualMomentumAlpha
10. CurveConditionedFlowAlpha
11. ClockConditionedFlowAlpha
12. FactorConfirmedFlowAlpha
13. FlowExhaustionReversalAlpha
```

## 22.2 Implement If News/Sentiment Data Exists

```text
14. IssuerNewsSentimentAlpha
15. NewsVolumeConditionedRVAlpha
16. NewsVolumeConditionedFlowReversalAlpha
17. MacroSentimentRegimeInteraction
18. TransientThemeFactorAlpha
```

## 22.3 Implement As Conditioning/Diagnostics

```text
19. CovarianceRegimeConditionedFlowAlpha
20. CovarianceRegimeConditionedRVAlpha
21. BetaInstabilityConditionedCrossAssetAlpha
```

---

## 23. First Feature Research Table

Produce one row per feature and horizon:

| Feature | Horizon | Coverage | IC | IC t-stat | OOS R2 lift | Top-bottom decile | Best split | Worst split | Classification | Promote |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| ClockAlpha |  |  |  |  |  |  |  |  |  |  |
| TripletAlpha |  |  |  |  |  |  |  |  |  |  |
| VRReversalAlpha |  |  |  |  |  |  |  |  |  |  |
| CurveToLevelSpilloverAlpha |  |  |  |  |  |  |  |  |  |  |
| BondCurveResidualAlpha |  |  |  |  |  |  |  |  |  |  |
| IssuerNewsSentimentAlpha |  |  |  |  |  |  |  |  |  |  |
| TransientThemeAlpha |  |  |  |  |  |  |  |  |  |  |
| CovRegimeConditionedAlpha |  |  |  |  |  |  |  |  |  |  |

---

## 24. Expected Best Candidates For Anonymous Corporate Bond RFQ Alpha

The most promising additions are:

```text
1. TripletMomentumReversalAlpha
2. ClockConditionedFlowAlpha
3. CurveToLevelSpilloverAlpha
4. BondCurveResidualAlpha
5. VarianceRatioReversalAlpha
6. FlowExhaustionReversalAlpha
7. FactorConfirmedFlowAlpha
```

Reason:

```text
They do not require client identity.
They do not require proprietary sentiment data.
They exploit the actual structure of corporate bonds:
  sparse trading,
  curve relationships,
  delayed fair-value adjustment,
  liquidity pressure,
  issuer/sector spillovers.
```

The news and sentiment features are useful, but only after data availability is confirmed.

