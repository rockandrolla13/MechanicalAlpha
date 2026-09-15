# Bond Momentum Signal: Findings, Test Plan and Next Steps

*Standalone copy of the LLMWikiGeneration wiki analysis page `wiki/wiki/analyses/bond-momentum-signal-design-and-testing.md` (2026-09-15). Source names refer to pages in that wiki.*

**Goal.** A momentum feature for corporate bonds that predicts returns 1–3 months ahead. It is built to be one input among many in a larger signal universe, not a standalone strategy.

**Starting point.** A Barra-style decomposition of each bond's return into factor contributions plus an ISIN-level residual.

**How to read this note.**
- Plain statements come from the papers, checked against their text in this wiki. Page references point to the source pages linked at the end.
- **(inference)** marks my own reasoning, which no source tests.
- **(not in source)** marks details a paper leaves unstated, usually because the equation was lost in PDF conversion.

---

## 1. Summary

1. **Scale returns by risk before ranking.** In corporate bonds, standard momentum shows no premium (0.38% a year, t = 0.12). Dividing each bond's past return by its volatility gives 3.18% a year (t = 4.58). Volatility differs far more across bonds than across stocks.
2. **Residualising cuts risk sharply.** Ranking on residual returns roughly halves volatility and cuts the 2009 bond drawdown from −80% to −25%. It works better than hedging factor exposure after the portfolio is formed.
3. **But a residual only removes the factors in your model.** If a trending factor is missing, the residual carries that factor's momentum. What the signal measures depends on the factor set.
4. **At 1–3 month horizons the split matters.** On US stocks at one month, the firm-specific part of returns reverses while the systematic part continues. Nobody in this wiki has tested this on bonds. The recommendation is to build systematic and idiosyncratic momentum as separate features.
5. **DTS is a serious alternative to realised volatility as the denominator.** Duration times spread predicts bond volatility, both market-wide and bond-specific. It is forward-looking and needs no return history. Which denominator works better for *ranking* is untested, so test it first (Section 4.1).
6. **Data quality decides everything.** Bid-ask noise in TRACE prices can create or erase short-horizon momentum. Filters must be applied before the fact, not after.

---

## 2. What the Literature Says

### 2.1 How momentum signals are defined

| Source | Signal | Where volatility enters |
|---|---|---|
| Jostova et al. (2013) | Past 6-month bond return | None |
| Houweling & van Zundert (2017) | Past 6-month excess return over duration-matched Treasuries, 1-month lag, top and bottom 10% | None |
| Dickerson et al. (2024) | MOM(3,3), MOM(6,6), deciles | None |
| Daniel & Moskowitz (2016) | Cumulative return t−12 to t−2, deciles | Sizing only: forecast mean and variance of the long-short portfolio |
| Blitz, Huij & Martens (2011) | Fama–French 3-factor residual over the 12 months skipping the latest, divided by residual standard deviation over the same period | In the signal |
| Haesen, Houweling & van Zundert (2017) | Issuer's CAPM residual equity return: last J residuals compounded, divided by the standard deviation of all 36 residuals in the estimation window. J = 6, held 6 months | In the signal |
| van Zundert (2017) | Return divided by volatility; inverse-volatility weights; decile volatility held constant | Signal and sizing |
| Ehsani & Linnainmaa (2022) | Sign of a factor's past-year return; factors scaled to equal variance | Sizing only |
| Morgan Stanley BMI (2015) | Index level minus its 4-month EMA, divided by a 4-month EMA of absolute changes | In the signal |
| Morgan Stanley credit-BMI (2018) | Decaying 4-month moving average of high yield excess returns, divided by "a volatility metric" (not specified in source); 1-week lag | In the signal |
| Carver (2023) | Moving-average crossover divided by price volatility; forecast scaled to average absolute value 10 (scalar ≈ 1.9 for EWMAC(16,64)) | In the signal |

### 2.2 Volatility-adjusted momentum (van Zundert 2017)

**The argument.** For a mean-variance investor with equal correlations across assets, the best assets to hold are those with the highest Sharpe ratio. So rank on return divided by volatility, not raw return.

**Three steps.**
1. Sort on return / volatility.
2. Weight by 1 / volatility within each decile.
3. Lever each decile to constant volatility (c = 0.60; exact formula not in source).

**Stocks, 1927–2015.**

| Step | Sharpe ratio | Skew |
|---|---|---|
| Standard momentum | 0.34 | −3.91 |
| 1: sort on return / volatility | 0.79 | −0.64 |
| 2: add inverse-volatility weights | 0.85 | −1.17 |
| 3: add constant volatility | 1.14 | −1.02 |

- **Step 1 works through the losers.** The most volatile losers stop falling, so shorting them hurts. The volatility sort avoids them.
- **Step 3 works by balancing winner and loser volatility.** That alone lifts Sharpe from 0.85 to 0.97.
- **Timing comparison.** Timing the whole winner-minus-loser portfolio by its trailing volatility (Barroso & Santa-Clara) reaches 0.74. Both methods together reach 1.31.

**Corporate bonds (Barclays US investment grade and high yield constituents, 1994–2015).**
- **Signal:** excess return over duration-matched Treasuries, t−6 to t−1, scaled by the monthly standard deviation of excess returns over the past 12 months (skipping the latest). Equal-weighted deciles, held 6 months. The bond test does not state whether the step 2 and step 3 sizing is used (not in source).
- **Why bonds need it more:** the 90th/10th percentile ratio of volatility across assets is 14.2 for bonds against 3.1 for stocks.

| | Standard | Volatility-adjusted |
|---|---|---|
| Winners − losers, all bonds | 0.38% (t = 0.12), Sharpe 0.04 | 3.18% (t = 4.58), Sharpe 1.04 |
| Investment grade | −1.08% | 2.47% (t = 3.19) |
| High yield | 2.56% (t = 0.60) | 4.02% (t = 4.03) |

- Standard momentum is significant only for CCC and below.
- The volatility-adjusted version is significant in every rating group except AAA/AA; its A-rated alpha is not significant.
- No transaction costs are included.

### 2.3 Residual momentum

**Blitz, Huij & Martens (2011), stocks.**
- **Why it helps:** plain momentum carries time-varying factor bets. Residual ranking makes those exposures 3–5 times smaller and roughly doubles the Sharpe ratio, mainly through lower volatility.
- **What standardising adds:** without dividing by residual volatility, the strategy earns 11.88% a year at 13.28% volatility, Sharpe 0.89. The authors say standardising "in particular helps to further reduce the risk."
- **2000–2009:** total-return momentum lost 8.5% a year; residual momentum made 4.7%.

**Haesen, Houweling & van Zundert (2017), bonds ranked on issuer equity residuals.**
- **Why it matters:** default-beta exposure of plain momentum spillover depends on the equity market's direction during formation. It hurts when an equity bear market turns into a credit rally, as in 2009.
- **Residual ranking:** cuts volatility from 8.85% to 4.80%, raises Sharpe from 0.35 to 0.77, and cuts the 2009 drawdown from −80% to −25%.
- **Hedging after formation:** static, dynamic or rating–maturity hedges cut volatility only to 6.92%, 6.57% and 6.17%. Their Sharpe ratios are similar to residual ranking, and residual ranking combined with a hedge is best.
- **Residualising on all three Fama–French factors:** alpha slips from 4.43% to 3.98%, but the time-varying default beta falls further, from 1.31 (total) to 0.37 (market only) to 0.25 (three factors).

**Gap.** No source in this wiki residualises bonds' *own* returns for momentum.

### 2.4 The omitted-factor warning

**Ehsani & Linnainmaa (2022).**
- **Residuals inherit momentum.** They can show momentum even when true firm-specific returns are noise, if the model leaves out autocorrelated factors.
- **Stock evidence:** CAPM residual momentum earns 58 bps a month against 45 bps for raw returns, then falls to 44 bps and 37 bps on 3- and 5-factor residuals. None is significant after controlling for factor momentum.
- **Hidden low-beta bet:** residual strategies partly bet against beta, because a high residual can reflect a low estimated beta.

**Graef, Hoechle & Schmid (2025)** find the opposite over medium horizons on US stocks:
- sorting on firm-specific returns (t−12 to t−2) earns 0.571% a month (t = 3.24);
- sorting on systematic returns earns 0.200% (t = 1.00).

The wiki records this as unresolved: Factor momentum transmission.

**What it means for the signal (inference).** Your Barra residual contains momentum from any trending factor Barra leaves out, such as a sector or rating effect it doesn't model. So the factor set determines what "idiosyncratic momentum" means.

### 2.5 Short horizons (1–3 months)

- **Graef et al., stocks, one-month horizon:**
  - firm-specific returns *reverse*, −0.783% a month;
  - systematic returns *continue*, +0.383% (t = 2.19).
  - Residualising at a one-month horizon may keep the part that reverses (inference for bonds).
- **Dickerson et al.:** after correcting for bid-ask noise, the monthly short-term reversal premium in bonds falls from 0.90% to about zero. After correction, investment grade shows weak reversal and high yield shows momentum.
- **Houweling & van Zundert** test a 3-month formation as a robustness variant. **Dickerson et al.** test MOM(3,3).
- **Morgan Stanley credit-BMI:** a volatility-scaled 4-month momentum predicts the direction of next-month excess returns 62% of the time for investment grade and 61% for high yield. It is a market-timing signal, not a cross-sectional one, and it is slow to catch sharp reversals.
- **Main bond evidence uses 6-month holds.** van Zundert, Haesen and Jostova all hold 6 months. Nothing in the wiki shows their results at 1–3 months.

### 2.6 Duration times spread (Ben Dor et al. 2007)

**Data:** Lehman Brothers Credit Index, September 1989 to January 2005; 565,602 observations including Ba and B bonds.

**Findings.**
- **Proportional moves:** spread changes are proportional to spread level, not parallel. A proportional model explains 33% of spread variation against 16.9% for a parallel shift.
- **Volatility scales with spread:**
  - systematic spread volatility ≈ 9% of spread per month (9.1%, or 9.4% excluding outliers);
  - idiosyncratic spread volatility ≈ 11.5% of spread per month.
- **Excess-return volatility is linear in DTS:** slope 8.8%, R² 98%. Bonds with different spreads and durations but equal DTS have equal volatility.
- **Forecast calibration:** returns divided by (DTS × historical relative spread volatility) have a standard deviation of 1.01. Spread-duration forecasts give 1.14 (full history) or 0.92 (36 months). Returns beyond 2 standard deviations are 4.03% against 7.06%.
- **Where it breaks:** below about 20 bp spread, volatility flattens to a structural floor. For agencies it is 2.5–3.0 bp a month systematic and 4.0–4.5 bp idiosyncratic.
- **Pricing noise:** the authors warn DTS measures are sensitive to it.
- **Scope:** the paper studies risk, not return predictability.

### 2.7 Data pitfalls

- **Dickerson et al. (2024):**
  - most TRACE price-based signals are not corrected for microstructure noise;
  - winsorising after the fact inflates returns, especially in crises;
  - corrected data and code are published at openbondassetpricing.com (PyBondLab).
- **Jostova et al. (2013):** bond momentum profits come from non-investment-grade bonds, and removing the worst-rated 8% of observations removes the effect. A momentum signal can be a disguised distress bet.
- **Local data (from the marketdb notes):** the `trace` table covers 15 issuers from 2023-05-30 to 2025-09-30. That is too narrow and too short for cross-sectional momentum tests. A broad bond panel is required.

---

## 3. Proposed Signal Design

**Timing notation.** Month t is the signal date. The formation window is J months, ending at t−1, with month t skipped. The forecast target is the return over t+1 to t+h, with h = 1, 2 or 3. The skip is a choice to test (Section 4.5).

The design is three features, kept separate so the combiner can weight them (inference; supported by the conflict in Sections 2.4–2.5).

### Feature 1: Systematic momentum

```
SYS_i,t   = Σ over m in formation window of  Σ over Barra factors k of  β_ik,m × f_k,m
score_SYS = SYS_i,t / D_i,t
```

It captures momentum in the factors a bond is exposed to (sector, rating, spread level). Ehsani & Linnainmaa and Li et al. support this component on stocks.

### Feature 2: Idiosyncratic momentum

```
RES_i,t   = Σ over m in formation window of  e_i,m      (Barra residual)
score_RES = RES_i,t / D_i,t
```

This is the bond-level analogue of Blitz et al. and Haesen et al.

- **Denominator choice:** Blitz uses residual volatility over the formation window; Haesen uses the whole 36-month estimation window. Test both.
- **Summing or compounding:** Haesen compounds residuals. For monthly bond residuals the difference is small (inference); pick one and keep it fixed.

### Feature 3: Equity spillover (optional)

```
score_SPILL = compounded CAPM residual equity return of the issuer (last J months)
              / std of the 36 residuals in the estimation window
```

- **Source:** Haesen et al.
- **Advantage:** it never uses bond prices, so bond bid-ask noise can't enter it.
- **Limit:** it covers only issuers with listed equity.

### Denominator candidates, D_i,t

| Candidate | Definition | For |
|---|---|---|
| Realised volatility | Standard deviation of monthly excess returns (Feature 1) or residuals (Feature 2) over t−12 to t−1 | van Zundert, Blitz |
| DTS | Spread duration × spread at t, times a constant k estimated from past data | Ben Dor |
| Blend | Geometric or arithmetic mix of the two | Only if Section 4.1 Test 3 shows both add value |

Apply a volatility floor, or rank within duration buckets, to stop near-zero denominators from dominating (inference; no source addresses this).

---

## 4. Test Plan

### 4.0 Data requirements

- A broad panel of bonds (investment grade and high yield), monthly, covering many years and at least one full credit cycle.
- Excess returns over duration-matched Treasuries, and the Barra factor contributions and residuals at ISIN level.
- Returns corrected for bid-ask noise, following Dickerson et al.
- Spread, spread duration, rating, sector, amount outstanding, and a liquidity measure, all known at each month-end.
- Issuer equity returns, for Feature 3.
- **Point-in-time discipline:** every input must be known at month-end t. Filters are applied ex ante only.

### 4.1 Test A: which denominator predicts next-month volatility?

**The problem.** A single bond's next-month volatility is not observable from one return.

**The trick (Ben Dor).** Divide next-month outcomes by the forecast and check the result across many bonds and months.

**Setup, one row per ISIN per month:**
- **Target:** e(t+1), the next-month Barra residual. Repeat with total excess return for Feature 1.
- **Forecast A:** standard deviation of the bond's monthly residuals over t−11 to t. Require at least about 9 observations.
- **Forecast B:** k × DTS at t. Estimate k from the prior 36 months only, as the pooled standard deviation of e / DTS. Ben Dor's estimate for idiosyncratic moves is about 11.5%.
- **Common sample:** evaluate both on the same bond-months.

**Test A1: ranking.** This is the decision test, because the momentum score only needs *relative* volatility.
- Each month, compute the Spearman rank correlation between the forecast and |e(t+1)|.
- Average over months, with a t-statistic from the monthly series.
- The higher average wins.

**Test A2: calibration across the range.**
- Each month, sort into 10 buckets by forecast.
- Per bucket, compute the standard deviation of e(t+1) and the mean forecast.
- Plot realised against forecast. A good forecast lies on a 45° line.
- For DTS, look at the bottom bucket: Ben Dor find flattening below about 20 bp.

**Test A3: does each add over the other?**
- Each month, regress log|e(t+1)| on log A and log B together.
- If one coefficient dies, drop that denominator. If both survive, test a blend.

**Test A4: overall calibration.**
- Compute z = e(t+1) / forecast.
- Report the standard deviation of z (target 1) and the share of |z| > 2.
- Ben Dor benchmarks: 1.01 and 4.03% for DTS; 1.14 and 7.06% for absolute spread volatility.

**Repeat all four** with the 3-month forward residual sum as the target.

**Report by subgroup:** rating (investment grade / high yield / CCC and below), liquidity tercile, spread below 20 bp. If DTS wins only among illiquid bonds, the likely reason is that noise inflates realised volatility there, not that DTS forecasts better (inference).

### 4.2 Test B: does each feature predict returns at 1–3 months?

For each feature, each denominator and each formation window J:

1. **Information coefficient (IC).** Each month, compute the Spearman rank correlation between the score and the return over t+1 to t+h, for h = 1, 2, 3. Report the mean IC, its t-statistic, and the share of months with positive IC.
   - Target for Feature 1: excess return.
   - Target for Feature 2: both excess return and next residual.
2. **Decay profile.** Plot mean IC against h. A feature useful for 1–3 months should not reverse sign within that range.
3. **Portfolio sort, as a diagnostic.** Form quintile or decile long-short portfolios. For h > 1, use overlapping portfolios as in Jegadeesh–Titman and van Zundert. Report return, t-stat, Sharpe and skew. This is a test of the feature, not a strategy.
4. **Benchmarks each feature must beat:**
   - raw excess-return momentum, same window;
   - van Zundert volatility-adjusted momentum, same window.

### 4.3 Test C: is the signal new, or a known factor in disguise?

Regress each feature's long-short returns, or its IC series, on these controls. Report the remaining alpha.

| Control | Why | Source |
|---|---|---|
| Momentum in your own Barra factors (sign of each factor's past return) | Separates bond-specific momentum from factor momentum | Ehsani & Linnainmaa |
| Low-risk factor (short-maturity, highly rated bonds) | Residual strategies implicitly bet against beta | Ehsani & Linnainmaa; Houweling & van Zundert |
| Default and term factors | Time-varying default beta | Haesen et al. |
| Short-term reversal | 1-month momentum can be reversal with the sign flipped | Dickerson et al. |
| The other signals in the universe | Incremental value is what counts | — |

Also report the correlation between the three features, and each feature's correlation with the existing signals.

### 4.4 Test D: robustness

- **Rating:** separately for investment grade, BB–B and CCC-and-below, and for the full sample excluding CCC-and-below. This tests Jostova's finding that momentum sits in distressed bonds.
- **Liquidity:** separately by liquidity tercile.
- **Noise correction:** with and without Dickerson's correction. A feature that only works uncorrected is an artefact.
- **Regimes:** IC by year and by credit regime (spread widening versus tightening). Hu & Zhang's screen: a useful indicator should have a stable relationship with future returns, show persistence, and keep the *same sign* across regimes. A sign flip disqualifies it.
- **Spread level:** separately for bonds below 20 bp, where DTS breaks down.
- **Factor set (inference):** rebuild the residual with and without sector and rating factors. If Feature 2's IC changes a lot, the residual was carrying omitted-factor momentum.

### 4.5 Fix the grid before looking at results

| Dimension | Values |
|---|---|
| Formation window J | 3, 6, 12 months |
| Skip | 0 or 1 month |
| Denominator | realised volatility (formation window), realised volatility (36 months), DTS, blend (only if Test A3 supports it) |
| Horizon h | 1, 2, 3 months |
| Features | SYS, RES, SPILL |

Report every cell, not only the best. Ehsani & Linnainmaa note that a data-mined subset of factors reached t = 8.24 against 6.21 for the full set, so choosing the best cell after the fact overstates the result.

### 4.6 Bias checklist

- [ ] Every input known at month-end t (spreads, ratings, Barra exposures, k).
- [ ] Filters applied before formation only; no winsorising of future returns.
- [ ] Returns corrected for bid-ask noise.
- [ ] Defaulted bonds kept, using their last traded price.
- [ ] New issues handled the same way under both denominators (common sample).
- [ ] Rank-based statistics used where |returns| are heavy-tailed.
- [ ] No parameter chosen on the test period.

---

## 5. Steps to Improve the Signal

In order; each step must pass before the next.

1. **Get the data right.** Build a broad, noise-corrected, point-in-time bond panel. The local 15-issuer TRACE table is not enough.
2. **Replicate the benchmark.** Reproduce van Zundert's volatility-adjusted bond momentum (6-month window) on your panel. If it doesn't reproduce, stop and find out why before building anything on top.
3. **Choose the denominator.** Run Test A. Pick the winner on ranking (A1); use A2 and A3 to find where it fails and whether a blend helps. Put a floor on very small denominators.
4. **Split the signal.** Build systematic, idiosyncratic and (optionally) equity-spillover features from the Barra decomposition.
5. **Test the horizon.** Run Test B for 1, 2 and 3 months across the fixed grid. Keep only feature–window combinations whose IC doesn't change sign within 1–3 months.
6. **Remove known factors.** Run Test C. Keep a feature only if it adds value beyond factor momentum, low risk, reversal and the existing signals.
7. **Stress it.** Run Test D. Drop any feature that works only in CCC-and-below bonds, only without the noise correction, or with a sign that flips across regimes.
8. **Revisit the factor set.** If Feature 2 depends heavily on which factors are removed, decide on purpose which trending factors belong in the residual model, then re-run steps 5–7.
9. **Hand over clean features.** Pass standardised cross-sectional scores (ranks or z-scores) to the combiner. Sizing and leverage (van Zundert steps 2–3) belong to portfolio construction, not to the feature.

---

## 6. Open Questions

- Does Graef et al.'s one-month result (firm-specific returns reverse, systematic ones continue) hold in corporate bonds?
- Does DTS scaling beat realised-volatility scaling for *return prediction*, not just volatility forecasting? No source in this wiki tests it.
- How much of van Zundert's bond result survives at 1–3 month holding periods and after bid-ask correction?
- Which Barra factors trend over 1–3 months? Their factor momentum is itself a candidate feature.

---

## 7. Sources in This Wiki

- van Zundert (2017) — volatility-adjusted momentum, stocks and bonds
- Blitz, Huij & Martens (2011) — residual momentum
- Haesen, Houweling & van Zundert (2017) — residual momentum spillover to bonds
- Ehsani & Linnainmaa (2022) — factor momentum and the omitted-factor warning
- Graef, Hoechle & Schmid (2025) — firm-specific versus systematic momentum
- Li, Yuan & Zhou (2025) — systematic momentum
- Daniel & Moskowitz (2016) — momentum crashes and dynamic scaling
- Jostova et al. (2013) — bond momentum sits in non-investment grade
- Houweling & van Zundert (2017) — bond factor definitions, including DTS low-risk
- Dickerson, Robotti & Rossetti (2024) — noise and filtering pitfalls
- Ben Dor et al. (2007) — DTS
- Morgan Stanley credit-BMI (2018) and Bond Market Indicators (2015) — volatility-scaled market momentum
- Carver (2023) — volatility-normalised trend forecasts
- Hu & Zhang (2025) — indicator screening criteria

Related: Bond Momentum · Residual Momentum · Factor Momentum · Duration Times Spread · Factor momentum transmission
