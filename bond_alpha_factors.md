# Alpha-Prediction Factors for Corporate Bonds

*A compendium of signals extracted from limit-order-book microstructure and formulaic alpha-mining literature, translated to an OTC bond tape. Scope: prediction of future price/spread changes only — quote-placement, execution-scheduling, and market-making control content is excluded, though predictive state variables arising inside those frameworks are retained.*

---

## 1. Data model, clocks, and notation

**Instruments and tape.** For bond $b$ the trade tape is a marked point process $\{(t_k, P_k, V_k, d_k)\}$: execution time, clean price, par volume, and direction flag $d_k \in \{+1\ (\text{customer buy}),\ -1\ (\text{customer sell}),\ 0\ (\text{interdealer})\}$ (TRACE-style). Where available, a composite quote process supplies bid $P^B_t$, ask $P^A_t$, contributed sizes $q^B_t, q^A_t$ (aggregated dealer axes or CBBT/CP+-style composites). Mid $m_t = \tfrac12(P^B_t+P^A_t)$; quoted spread $s_t = P^A_t - P^B_t$. When quotes are unavailable, replace the mid by a robust trade-based fair value (F15–F18) and the spread by the realized effective spread (F22).

**Returns.** $r_{t,\delta} = P_{t+\delta}/P_t - 1$ in price space; sign-flip for spread space (OAS changes).

**Clocks** (essential for bonds — calendar time is mostly empty):

- **Time clock:** last $\delta$ units of calendar time.
- **Volume clock:** most recent prints totalling $V^\*$ par volume.
- **Transaction clock:** last $k$ prints.

**Fallback-window rule** (from the sparse-orderbook electricity literature): given nested horizons $\delta_1 < \dots < \delta_W$, compute each feature on the shortest window containing at least one print; discard only if the full-history window is empty. Record which horizon supplied the data — the realized horizon is itself a staleness feature.

**Operator grammar** (from the alpha-mining papers):

| Operator | Type | Meaning |
|---|---|---|
| $\mathrm{Ref}(x,t)$, $\Delta(x,t)=x-\mathrm{Ref}(x,t)$ | TS | lag; $t$-period difference |
| $\mathrm{Mean}$, $\mathrm{Med}$, $\mathrm{Sum}(x,t)$ | TS | rolling mean / median / sum |
| $\mathrm{Std}$, $\mathrm{Var}$, $\mathrm{Mad}(x,t)$ | TS | rolling dispersion; $\mathrm{Mad}=\mathbb{E}|x-\mathbb{E}x|$ |
| $\mathrm{Min}$, $\mathrm{Max}(x,t)$ | TS | rolling extremes |
| $\mathrm{WMA}$, $\mathrm{EMA}(x,t)$ | TS | weighted / exponential moving average |
| $\mathrm{Corr}$, $\mathrm{Cov}(x,y,t)$ | TS | rolling correlation / covariance |
| $\mathrm{TsRank}(x,t)$ | TS | rank of current value within its own last $t$ values |
| $\mathrm{CsRank}(x)$ | CS | cross-sectional rank across bonds on a date |
| Greater, Less, IfElse, Abs, Log, sgn | CS | elementwise |

Cross-sectional ranking should be done **within homogeneous buckets** (rating × maturity × sector, or versus issuer curve).

---

## 2. Signed-flow and trade-sign factors

### F1 — Last-trade sign  [Muni Toke–Yoshida]

$$\epsilon_t = d_{k(t)}, \qquad k(t) = \max\{k : t_k \le t,\ d_k \ne 0\}.$$

*Intuition.* Order flow is autocorrelated: the sign of the most recent customer trade predicts the sign of the next one and the direction of the next price adjustment. Model selection in the intensity-ratio study never drops this covariate.
*Bond translation.* Direct from the TRACE buy/sell flag; decay by time-since-last-trade (F3) rather than using the raw sign indefinitely.

### F2 — Signed-spread interaction  [Muni Toke–Yoshida]

$$X_t = s_t\,\epsilon_t \qquad \text{or, in regime form,}\qquad X_t = \mathbb{1}\{s_t > \bar s\}\,\epsilon_t.$$

*Intuition.* Empirically, when the spread is wide the imbalance signal flattens and **the last trade sign's persistence strengthens**. The interaction carries the information; model selection retains $(i,\epsilon,s\epsilon)$ and essentially never $(i,\epsilon,s)$.
*Bond translation.* Bonds are a permanently wide-spread market, so sign-persistence terms should be up-weighted relative to imbalance terms; the interaction lets the data set the mix per bond.

### F3 — Exponentially decayed signed flow (flow pressure)  [Hawkes covariates; Bank–Cartea–Körber]

$$F_t(\beta) = \sum_{t_k \le t} e^{-\beta(t-t_k)}\, d_k V_k, \qquad \beta \in \{\beta_{\text{fast}}, \beta_{\text{med}}, \beta_{\text{slow}}\}$$

(half-lives ≈ 1 day / 1 week / 1 month for bonds).
*Intuition.* Scalar summary of mutually exciting order-flow intensities: recent net customer buying predicts continued buying and upward adjustment at short horizons, and reversion at long horizons once flow is inventory-driven (F13).
*Bond translation.* Signed par volume normalized by amount outstanding (or trailing volume). The pair $(F_t(\beta_{\text{fast}}), F_t(\beta_{\text{slow}}))$ separates continuation from reversion horizons.

### F4 — Per-type Hawkes intensity covariates  [Muni Toke–Yoshida]

For each flow type $i$ (customer buy / customer sell / interdealer; optionally aggressive vs. non-aggressive by whether the print is at/through the far quote):

$$H_i(t) = \log\Big(\mu_i + \int_0^t \alpha_i\, e^{-\beta_i(t-u)}\, dN^i_u\Big),$$

with $(\mu_i,\alpha_i,\beta_i)$ fitted by MLE per bond or pooled per liquidity bucket.
*Intuition.* The fitted excitation state of each order type is a covariate: elevated buy-side intensity relative to sell-side intensity predicts the side of the next trade. In the marked-point-process study, covariate sets (imbalance + aggressive-buy/sell + total buy/sell Hawkes states) dominate model selection.
*Bond translation.* Fit on TRACE arrival times per side; for very sparse bonds pool the parameters within issuer/rating bucket and keep only the state $H_i(t)$ bond-specific.

### F5 — Buy/sell separated print streams and their gap  [OrderFusion]

$$\mathrm{VWAP}^{+}_{[t-\delta,t]} = \frac{\sum_{k:d_k=+1} P_k V_k}{\sum_{k:d_k=+1} V_k}, \qquad \mathrm{VWAP}^{-}\ \text{analogously},$$

$$G_t = \mathrm{VWAP}^{+} - \mathrm{VWAP}^{-}\ \ (\text{realized effective spread, F22}), \qquad
\Pi_t = \frac{\sum_{d_k=+1} V_k - \sum_{d_k=-1} V_k}{\sum_{d_k\ne 0} V_k}\ \ (\text{volume pressure}).$$

*Intuition.* Aggregating the two sides into one series destroys the buy–sell interaction structure, where much of the predictive content lives (the electricity work encodes the sides as two separate 2-D streams for exactly this reason).
*Bond translation.* TRACE side flags make this free; $\Pi_t$ is the trade-based analogue of book imbalance.

---

## 3. Imbalance and quote-based factors

### F6 — Best-quote imbalance  [Lehalle–Neuman; Muni Toke–Yoshida $Z_1$; Palguna–Pollak SI]

$$I_t = \frac{q^B_t - q^A_t}{q^B_t + q^A_t} \in [-1,1].$$

*Intuition.* Excess standing bid-side size predicts an upward next move; empirically the signal behaves like a mean-reverting Ornstein–Uhlenbeck process, $dI_t = -\gamma I_t\,dt + \sigma_I\,dW_t$, so its value decays at half-life $\log 2/\gamma$ — this calibrates the usable prediction horizon.
*Bond translation.* Replace queue sizes with (i) counts/sizes of dealer axes bid-wanted vs. offered, (ii) direction imbalance of recent inquiry flow, or (iii) size asymmetry among composite-quote contributors. Weaker than in a firm-quote LOB (indicative quotes), but the OU decay structure carries over.

### F7 — Multi-level, multi-lookback book-pressure grid  [Li et al.]

$$\mathrm{OBP}(n,\ell)_t = \frac{\sum_{\tau=0}^{n}\sum_{j=1}^{\ell}\mathrm{BidSize}_{j,t-\tau}}{\sum_{\tau=0}^{n}\sum_{i=1}^{\ell}\mathrm{AskSize}_{i,t-\tau}},$$

computed on a grid of lookbacks $n$ and depth levels $\ell$, fed **as a vector** to a classifier (no single calibration).
*Intuition.* Persistent one-sided pressure across levels and time predicts the mid direction; letting the learner weight the grid avoids committing to one parameterization.
*Bond translation.* Replace "levels" with **dealers**: aggregate axe/quote size across contributing dealers, lookbacks $\{1,5,21\}$ days.

### F8 — Order-flow imbalance (event-signed quote changes)  [Palguna–Pollak, after Cont et al.]

At quote-update events $T_i$:

$$e_{i+1} = \mathbb{1}\{P^B_{i+1}\ge P^B_i\}q^B_{i+1} - \mathbb{1}\{P^B_{i+1}\le P^B_i\}q^B_i - \mathbb{1}\{P^A_{i+1}\le P^A_i\}q^A_{i+1} + \mathbb{1}\{P^A_{i+1}\ge P^A_i\}q^A_i,$$

$$\mathrm{OFI}_t = \sum_{i=t-E+1}^{t} e_i.$$

*Intuition.* Signed **changes** in posted supply/demand — not standing levels — measure the net arrival of buying vs. selling interest.
*Bond translation.* Apply to the composite bid/ask: a dealer lifting their contributed bid is information even with no print. Event-clocked, hence robust to sparsity.

---

## 4. Reversal and price-pressure factors

### F9 — Moving-average deviation reversal  [FactorMiner 002/006]

$$X_t = -\frac{P_t - \mathrm{EMA}(P,n)_t}{\mathrm{EMA}(P,n)_t} \qquad\text{and}\qquad X_t = -\frac{P_t - \mathrm{VWAP}_{[t-\delta,t]}}{\mathrm{VWAP}_{[t-\delta,t]}}.$$

*Intuition.* Prints away from fair value are dealer-intermediated liquidity events whose price concession is recouped.
*Bond translation.* Trade-print price vs. VWAP of recent TRACE prints (volume clock); horizon days-to-weeks. Among the most robust documented corporate-bond alphas.

### F10 — Volume-conditioned reversal  [FactorMiner 004/008]

$$X_t = \mathrm{CsRank}\Big(\frac{V_t}{\mathrm{Mean}(V,n)_t}\Big)\cdot \mathrm{CsRank}(-r_t)
\quad\text{or}\quad
X_t = -\mathrm{CsRank}\Big(\frac{r_t}{\mathrm{Std}(r,n)_t+\varepsilon}\Big)\cdot \mathrm{CsRank}\Big(\frac{V_t}{\mathrm{Mean}(V,n)_t}\Big).$$

*Intuition.* Reversal is strongest after abnormal-volume moves: those are predominantly liquidity demand, and the provider's compensation is the reversion. The second form standardizes the return by its own volatility first.
*Bond translation.* TRACE volume spike × price drop ⇒ buy; normalize volume by amount outstanding. **The single highest-conviction transfer in this document.**

### F11 — Range-position (stochastic-oscillator) reversal  [FactorMiner 001/005/018]

$$K_t(n) = \frac{P_t - \mathrm{Min}(P,n)_t}{\mathrm{Max}(P,n)_t - \mathrm{Min}(P,n)_t + \varepsilon} \in [0,1], \qquad X_t = -\mathrm{CsRank}\big(K_t(n)\big),$$

optionally interacted with $\mathrm{TsRank}$ of volume or of $\mathrm{Cov}(r,V,n)$.
*Intuition.* Position in the recent range proxies over-extension.
*Bond translation.* Works on weekly bars where sparsity forces coarse sampling; combine with F16 extremes.

### F12 — Conditional reversal/momentum switch  [FactorMiner 019/031/034]

$$X_t = \mathrm{IfElse}\Big(\Big|\tfrac{P_t-\mathrm{VWAP}_t}{\mathrm{VWAP}_t}\Big| > c,\ -\mathrm{CsRank}(P_t - \mathrm{Max}(P,n)_t),\ -\mathrm{CsRank}(P_t - \mathrm{Min}(P,n)_t)\Big).$$

*Intuition.* When price is dislocated beyond a threshold, fade the extreme; otherwise trade drift toward the range boundary — a regime switch between pressure-reversion and drift.
*Bond translation.* Set $c$ in spread terms (fraction of typical bid–offer).

### F13 — Impact-state de-pressured value (propagator residual)  [Webster / Obizhaeva–Wang]

$$dI_t = -\beta I_t\,dt + \lambda\,dQ_t,\qquad dQ_t = d_k V_k\ \text{at print times} \ \Rightarrow\ I_t = \lambda \sum_{t_k\le t} e^{-\beta(t-t_k)} d_k V_k = \lambda F_t(\beta),$$

$$\widehat P_t = P_t - I_t, \qquad X_t = -I_t, \qquad \mathbb{E}[r_{t,h}] \approx -I_t\,(1-e^{-\beta h})/P_t.$$

*Intuition.* Observed price = fundamental + transient impact; the transient part decays at rate $\beta$, so reversal **is** impact decay — F9's model-based twin. The structural result is **myopia**: for a large model class the flow → expected-reversion mapping is a simple function of the impact level and decay rate; no dynamic optimization is needed to use it as a predictor.
*Bond translation.* $\beta$ is slow (days); estimate $(\lambda,\beta)$ per liquidity bucket by regressing future returns on decayed signed flow across horizons.

### F14 — Price–volume rank divergence  [FactorMiner 003/020/032]

$$X_t = \mathrm{CsRank}\big(\Delta(V,k)_t\big) - \mathrm{CsRank}\Big(\tfrac{P_t-\mathrm{VWAP}_t}{\mathrm{VWAP}_t}\Big),$$
$$X_t = -\mathrm{TsRank}\Big(\mathrm{CsRank}(\Delta(r,2)) - \mathrm{CsRank}(\Delta(V,2)),\ n\Big),$$
$$X_t = -\mathrm{TsRank}\Big(\mathrm{Cov}\big(\mathrm{TsRank}(P,n), \mathrm{TsRank}(V,n), k\big),\ n\Big)\cdot \mathrm{TsRank}\big(K_t(n), n\big).$$

*Intuition.* Volume rising without price confirmation flags accumulation/distribution; sustained price-volume rank co-movement near the range top flags exhaustion.
*Bond translation.* Weekly TRACE aggregates; computationally free once F9–F11 exist.

---

## 5. Fair-value statistics on a sparse tape

Headline empirical prior from the sparse-orderbook electricity studies (nested lookbacks + $\ell_1$ selection): **price percentiles (~30% of selected importance), minima (~26%), maxima (~22%) dominate; volume statistics contribute little; medium lookbacks beat the shortest window** (the freshest print is noisy).

### F15 — Trade-price percentiles  [orderbook feature learning]

$$Q^{(p)}_t(\delta) = \mathrm{percentile}_p\{P_k : t_k \in [t-\delta,t]\},\qquad p\in\{10,25,45,50,55,75,90\}\%,$$

per side (buy / sell / all). Factors: $Q^{(50)}$ as fair value; $(P_t - Q^{(50)}_t)/Q^{(50)}_t$ as robust reversal; $Q^{(75)}-Q^{(25)}$ as dispersion/liquidity state.
*Bond translation.* The median of recent TRACE prints is a matrix-price-free fair value.

### F16 — Rolling extremes and their spread

$$\mathrm{Min}(P,\delta)_t,\quad \mathrm{Max}(P,\delta)_t,\quad R_t(\delta)=\mathrm{Max}-\mathrm{Min},$$

used directly, inside $K_t$ (F11), and as the volatility proxy $R_t/Q^{(50)}_t$.

### F17 — Nested-window VWAPs and first/last prices  [OrderFusion; orderbook feature learning]

$$\mathrm{VWAP}_{[t-\delta_w,t]},\ P^{\text{last}}_t(\delta_w),\ P^{\text{first}}_t(\delta_w),\qquad \delta_w \in \{1,5,21,63\}\ \text{trading days},$$

per side and combined, with the fallback rule.
*Intuition.* The medium-window VWAP is the strongest single fair-value estimate in the sparse-market studies; the last print is weakly efficient but noisy. Provide the **vector** across windows and let a sparse learner pick.

### F18 — Liquid-to-illiquid signal propagation  [asymmetric generalization]

For illiquid bond $b$ of issuer $j$ with most liquid sibling $L(j)$:

$$X^{(b)}_t = X^{(L(j))}_t\ \text{for any factor above},\qquad Z_t = \tilde P^{(b)}_t - \big(\text{curve-implied price from } L(j)\big).$$

*Intuition.* The empirical asymmetry: features/models estimated on the liquid market transfer to the illiquid one, **not the reverse**. Estimate on liquid bonds, propagate along the issuer curve, trade the illiquid sibling's convergence.

---

## 6. Liquidity, illiquidity, and resilience factors

### F19 — Amihud illiquidity  [FactorMiner 013; standard credit literature]

$$\mathrm{ILLIQ}_t(n) = \mathrm{Mean}\Big(\frac{|r_k|}{V_k},\ n\Big)_t.$$

Priced characteristic (liquidity premium) and a conditioning variable for all flow factors (impact $\lambda$ in F13 ∝ it).

### F20 — Resilience (illiquidity improvement)  [FactorMiner 014]

$$X_t = \Delta_k\left(\frac{\mathrm{Mean}(|r|/V,\ n)_t}{|r_t|/V_t + \varepsilon}\right).$$

*Intuition.* The **dynamics**, not the level: improving price-per-volume sensitivity means flow is being absorbed; deteriorating resilience predicts spread widening.

### F21 — Amount-efficiency family  [FactorMiner 073–099]

$$\mathrm{AmtEff}_t = \frac{|r_t|}{\mathrm{Turnover}_t+\varepsilon},\qquad \text{velocity}=\Delta_k\,\mathrm{AmtEff},\qquad \text{acceleration}=\Delta_k^2\,\mathrm{AmtEff},$$

turnover = volume / amount outstanding. Refinements of F19; keep one or two, orthogonalized against F19.

### F22 — Realized effective spread  [OrderFusion side separation]

$$S^{\mathrm{eff}}_t(\delta) = \mathrm{VWAP}^{+}_{[t-\delta,t]} - \mathrm{VWAP}^{-}_{[t-\delta,t]}.$$

*Intuition.* Realized cost of immediacy with no quote data; widening predicts higher required returns and marks stress regimes where reversal factors pay more.

### F23 — Expected time-to-next-trade  [Palguna–Pollak $\mathbb{E}[\tau\,|\,S]$]

$$X_t = \widehat{\mathbb{E}}[\tau_t \mid S_t],\qquad \tau_t = \inf\{u>0: \text{print at } t+u\},$$

estimated nonparametrically over states (F33) or with a hazard model on time-since-last-trade.
*Intuition.* A liquidity factor (staleness risk) and a gate: horizons shorter than $\widehat{\mathbb{E}}[\tau]$ are not tradable.

### F24 — Quote-update intensity  [toxic-flow feature (c)]

$$U_t(\delta) = \#\{\text{composite-quote revisions in } [t-\delta,t]\}.$$

Dealer quote-revision activity leads trade activity; a burst of revisions with no prints signals imminent repricing.

---

## 7. Momentum and trend-reliability factors

### F25 — Studentized (t-stat) momentum  [FactorMiner 023]

$$X_t = \mathrm{TsRank}\left(\frac{\Delta(P,k)_t}{\mathrm{Mean}(|\Delta(P,k)|,\ n)_t},\ n\right).$$

*Intuition.* Trend divided by its typical absolute size: signal-to-noise-scaled momentum.
*Bond translation.* Apply to OAS changes; 3–6 month spread momentum is a documented credit factor, and studentization suppresses stale-price artifacts.

### F26 — Trend-reliability ($R^2$) weighting  [FactorMiner 080/083/085/090]

Regress (log) price on time over the window → slope $\hat\beta_t$, fit $R^2_t$:

$$X_t = \mathrm{sgn}(\hat\beta_t)\cdot R^2_t \qquad\text{or}\qquad X_t = \mathrm{CsRank}(\hat\beta_t)\cdot \mathrm{CsRank}(R^2_t).$$

*Intuition.* A trend that explains its own path is more likely information-driven and continues; a low-$R^2$ "trend" is pressure and reverts. A data-driven split between the momentum and reversal families.

### F27 — Cross-sectional lead–lag rank momentum  [FactorMiner 010/024/025]

$$X_t = -\mathrm{CsRank}\Big(\mathrm{CsRank}(P_t/P_{t-k}) - \mathrm{CsRank}(V_t/V_{t-k})\Big),$$
$$X_t = \mathrm{TsRank}\big(\Delta(P^{\text{first}},k),n\big) - \mathrm{TsRank}\big(\Delta(P^{\text{last}},k),n\big),$$

with $P^{\text{first}},P^{\text{last}}$ first/last prints per bar (open/close analogues).
*Intuition.* Divergence between where the bar opens and closes, or between price and volume ranks, captures intrabar pressure direction.

---

## 8. Volatility and higher-moment factors

### F28 — Realized volatility and inverse-vol tilt  [toxic-flow feature (a); FactorMiner 009/015]

$$\sigma_t(n) = \mathrm{Std}(r,n)_t,\qquad X_t = -\mathrm{CsRank}(r_t)\cdot\mathrm{CsRank}(\sigma_t(n)),\qquad X_t = -\mathrm{CsRank}(\sigma_t(n)).$$

(i) Core state variable in every predictive grid in the corpus; (ii) reversal amplified in high-vol names; (iii) low-volatility tilt — a documented credit anomaly.

### F29 — Volatility-of-volatility  [FactorMiner 077]

$$X_t = \mathrm{Std}\big(\sigma_\cdot(n),\ m\big)_t.$$

Instability of the volatility state flags regime transitions; rises ahead of downgrades and liquidity spirals.

### F30 — Rolling skewness / kurtosis regime switches  [FactorMiner 039/042–045/095]

$$\mathrm{Skew}_t(n),\ \mathrm{Kurt}_t(n)\ \text{of returns};\qquad X_t = \mathrm{IfElse}\big(\mathrm{Kurt}_t(n) > \kappa,\ -\mathrm{CsRank}(\Delta(P,k)),\ +\mathrm{CsRank}(\Delta(P,k))\big).$$

*Intuition.* Fat-tailed regimes favor fading moves; thin-tailed regimes favor following. Credit returns are structurally negatively skewed, so cross-sectional **differences** in rolling skew price crash exposure. Estimation noise is severe on sparse tapes: long windows, shrink toward bucket means.

---

## 9. Flow-toxicity and informed-flow factors

These originate in a broker's classification problem, but the **label** (does price move against the liquidity provider after the trade?) and the **features** are pure prediction objects: high predicted toxicity of observed flow is a directional signal that price keeps moving in the flow's direction.

### F31 — Markout label and toxicity propensity  [Cartea–Duran-Martin–Sánchez-Betancourt]

For a print at $t$ with direction $d$, markout horizon $G$:

$$M_{t,G} = d\cdot(m_{t+G} - m_t),\qquad y_t = \mathbb{1}\{M_{t,G} > c\},$$

fit $\widehat{\Pr}(y_t=1\mid x_t)$; the factor is toxicity-weighted signed flow:

$$X_t = \sum_{t_k\in[t-\delta,t]} \widehat{\Pr}(y_{t_k}=1\mid x_{t_k})\; d_k V_k.$$

**Feature grid** (183 features in the source): eight statistics — (a) mid volatility, (b) client trade count, (c) quote-update count, (d) mid return, (e)–(f) $\log(1+q^B)$, $\log(1+q^A)$, (g) spread, (h) imbalance — each under **three clocks** (time, volume, transaction) × seven nested lookbacks; plus level features (order size, spread and imbalance at arrival, last bid/ask/mid, cumulative activity counts, a volatility estimate) and the client's **historical toxicity proportion**. Transforms: $\mathrm{sgn}(x)\log(1+|x|)$ on signed magnitudes, $\log(1+x)$ on volumes.
*Bond translation.* $G$ of 1–5 days; mid replaced by the F15 fair value. Without client identity (public TRACE), substitute trade-size buckets and side-persistence; with an RFQ log, the historical-toxicity ratio is the strongest single feature.

### F32 — Client historical toxicity ratio

$$\rho^c_t = \frac{\#\{\text{toxic trades of client } c \text{ before } t\}}{\#\{\text{trades of client } c \text{ before } t\}}.$$

One line, outsized importance. A pooled model over all clients **with** client features beats per-client models — a data-efficiency lesson that transfers to per-bond vs. pooled factor models.

### F33 — VPIN  [Easley et al., via Li et al.]

Partition the tape into volume buckets of size $V^\*$; per bucket $n$ let $V^+_n, V^-_n$ be buy/sell volume:

$$\mathrm{VPIN}_t = \frac{1}{N}\sum_{n=1}^{N}\frac{|V^+_n - V^-_n|}{V^\*}.$$

Volume-clocked estimate of the informed share of flow; **unsigned**, so a risk/conditioning factor: predicts volatility and the profitability of reversal factors rather than direction.

### F34 — Informed-inventory signal (flow decomposition)  [Cartea–Sánchez-Betancourt]

Decompose flow with per-trade toxicity propensities (F31):

$$Q^{\mathcal I}_t = \sum_{t_k\le t} \widehat{\Pr}(y_{t_k}=1\mid x_{t_k})\,d_k V_k,\qquad Q^{\mathcal U}_t = \sum_{t_k\le t} \big(1-\widehat{\Pr}(y_{t_k}=1\mid x_{t_k})\big)\,d_k V_k,$$

$$X_t = +\mathrm{CsRank}(\Delta Q^{\mathcal I}_t)\ (\text{informed: continuation}),\qquad X_t = -\mathrm{CsRank}(\Delta Q^{\mathcal U}_t)\ (\text{uninformed: reversion}).$$

*Intuition.* The two components have opposite-signed predictive content; raw F3 averages them away.

---

## 10. Intensity-ratio probability factors

### F35 — Next-trade-side probability (Cox intensity ratio)  [Muni Toke–Yoshida, both papers]

Buy/sell intensities share an unobserved baseline:

$$\lambda^{\pm}(t) = \lambda_0(t)\exp\Big(\vartheta^{\pm}_0 + \sum_j \vartheta^{\pm}_j X_j(t)\Big),$$

which cancels in the ratio, leaving a logistic model with $\theta_j = \vartheta^+_j - \vartheta^-_j$:

$$p_t = \Pr(\text{next trade is a buy}\mid \mathcal F_t) = \Big(1+e^{-\theta_0-\sum_j\theta_j X_j(t)}\Big)^{-1},\qquad X_t = 2p_t - 1.$$

Covariates: imbalance (F6 / F5's $\Pi$), last sign (F1), signed spread (F2), Hawkes states (F4). Estimated by multinomial-logistic quasi-likelihood at event times.
*Intuition.* Ideal for bonds: the **level** of activity is wildly nonstationary (new issues, rebalances, macro prints) and lives in $\lambda_0$, which is never estimated; the relative buy-vs-sell propensity given the state is exactly what survives the ratio. Two selection lessons: imbalance alone is never the chosen model; the retained interaction is $s\epsilon$, not $s$.

### F36 — Two-stage side × aggressiveness ratios  [marked-point-process extension]

Stage 1: side probability $p_t$ (F35). Stage 2: conditional on side, probability the trade is aggressive $a^{\pm}_t$ (prints at/through the far composite quote), from a second ratio model. Directional factor:

$$X_t = p_t\,a^+_t - (1-p_t)\,a^-_t.$$

Aggressive prints carry the information; the same framework extends to predicting the size mark of the next trade (a flow forecast input to F13).

---

## 11. State-conditional nonparametric predictors

### F37 — Conditional moment grid over discretized states  [Palguna–Pollak]

State e.g. $S_t = (\lfloor\text{spread proxy}\rfloor,\ \lfloor\log(1+\text{time-since-last-trade})\rfloor,\ \mathrm{sgn}(\text{last flow}))$; estimate by historical averaging with $k$-NN smoothing across adjacent states (states with opposite imbalance/flow sign treated as infinitely distant):

$$\widehat{\Pr}[\Delta m_{t,\delta}\ne 0\mid S],\quad \widehat{\mathbb{E}}[\Delta m_{t,\delta}\mid S],\quad \widehat{\mathbb{E}}[\Delta m_{t,\tau}\mid S],\quad \widehat{\mathbb{E}}[\tau\mid S],$$

$\tau$ = time of first fair-value change (next print, for bonds). Two-stage prediction: move/no-move against a probability threshold, then the sign of the conditional mean.
*Intuition.* Assumption-free about functional form at the cost of state coarseness; the two-stage structure matches bond reality, where the modal short-horizon outcome is "no print." $\widehat{\mathbb{E}}[\tau\mid S]$ doubles as F23. Estimate within liquidity buckets, pooling bonds to populate cells.

---

## 12. Composite and machine-generated cross-sectional alphas

Representative mined expressions (RL/MCTS/agentic miners), translated to the bond tape ($\varepsilon$ guards throughout; $r$ bar returns, $V$ bar volume, $K_t(n)$ from F11, $R_t(n)$ from F16, $P^{\mathrm f}, P^{\mathrm l}$ first/last prints):

1. $X^{(1)}_t = -\mathrm{CsRank}\big(K_t(n)\big)$  — range-position fade
2. $X^{(2)}_t = \mathrm{CsRank}(\Delta(V,1)_t) - \mathrm{CsRank}\big(\tfrac{P_t-\mathrm{VWAP}_t}{\mathrm{VWAP}_t}\big)$  — volume-lead divergence
3. $X^{(3)}_t = -\mathrm{TsRank}(K_t(n), n)\cdot \mathrm{CsRank}\big(|\mathrm{Cov}(r,V,n)_t|\big)$  — range top × flow coupling
4. $X^{(4)}_t = -\mathrm{CsRank}\big(\tfrac{P_t-\mathrm{VWAP}_t}{\mathrm{VWAP}_t}\big)\cdot\big(1-\mathrm{CsRank}(V_t)\big)$  — low-volume dislocation fade
5. $X^{(5)}_t = -\mathrm{CsRank}\Big(\tfrac{\min(P^{\mathrm f}_t, P^{\mathrm l}_t) - \mathrm{Min}(P,n)_t}{R_t(n)+\varepsilon}\Big)$  — lower shadow / dip absorption
6. $X^{(6)}_t = -\mathrm{sgn}\big(\Delta(P,1)_t\big)\cdot\mathrm{TsRank}\big(\Delta(P,k)_t, n\big)$  — sign-conditional fade

Two structural lessons from the mining papers matter more than any expression. First, alphas are admitted **as a pool**: the objective is the performance of the optimized linear combination with mutual-correlation penalties, not individual ICs (Algorithm 7). Second, mined libraries **saturate** near ~100 factors — new candidates become near-duplicates — so a bond implementation should expect a small number of genuinely distinct families (roughly the sections of this document).

---

## 13. Reproduction algorithms (non-code)

**Algorithm 1 — Clock construction and fallback windows.**
1. Choose a clock: time (fixed $\delta$), volume (fixed par $V^\*$), or transaction (fixed count $k$). Prefer volume/transaction clocks for flow features, time clocks for calendar-aligned fair values.
2. For each observation time and each nested horizon $\delta_1<\dots<\delta_W$, collect prints in the window ending at $t$.
3. If a window is empty, fall back to the next longer horizon; mark missing only if the full-history window is empty.
4. Record which horizon supplied the data — the realized horizon is itself a staleness feature.

**Algorithm 2 — Decayed signed flow and impact state (F3, F13).**
1. Fix a half-life grid, e.g. $\{1,5,21\}$ trading days; $\beta = \log 2/\text{half-life}$.
2. Iterate prints in time order: $F \leftarrow F e^{-\beta\Delta t} + d_k V_k/\text{AmtOutstanding}$.
3. Estimate $(\lambda,\beta)$ per liquidity bucket: regress future $h$-day returns on $F_t(\beta)$ over a grid of $\beta$ and $h$; pick $\beta$ by out-of-sample fit; set $\lambda$ from the (negated) slope rescaled by $(1-e^{-\beta h})$.
4. Output $X_t = -\lambda F_t(\beta)$ and de-pressured value $P_t - \lambda F_t(\beta)$.

**Algorithm 3 — Markout labeling and toxicity propensity (F31–F32).**
1. Choose markout horizon $G$ (1–5 days) and materiality threshold $c$ (e.g. half the typical effective spread).
2. For every print, compute fair value at $t$ and $t+G$ (F15 median or composite mid); label $y=1$ if it moved in the trade's direction by more than $c$.
3. Build the feature grid: eight statistics × three clocks × nested horizons; append level features and, if known, the client historical-toxicity ratio; apply $\mathrm{sgn}(x)\log(1+|x|)$ / $\log(1+x)$ transforms.
4. Fit a calibrated classifier strictly walk-forward (the label needs $G$ of future data — embargo accordingly).
5. Score new prints; aggregate propensity-weighted signed volume over a trailing window (directional factor); split flow into informed/uninformed for F34.

**Algorithm 4 — Intensity-ratio (next-side) estimation (F35).**
1. Collect event times of customer buys and sells; pool sparse bonds within buckets.
2. At each event, record the covariate vector (imbalance/volume pressure, last sign, signed spread, Hawkes states, decayed flow).
3. Maximize the multinomial-logistic quasi-likelihood — equivalently, logistic regression of event side on covariates sampled **at event times**.
4. Select covariates with BIC-type criteria (AIC over-selects) or an $\ell_1$ penalty; expect $s\epsilon$ interactions to survive and single-covariate models to be rejected.
5. Output $X_t = 2\hat p_t - 1$, evaluated continuously between events.

**Algorithm 5 — Sparse fair-value feature selection (Section 5).**
1. Extract the full grid: percentiles, min, max, first, last, mean, VWAP, volatility, counts, volumes — per side and combined, per nested horizon (with fallback) — a few hundred candidates.
2. Standardize cross-sectionally within date and bucket.
3. Fit $\ell_1$-penalized regression (quantile regression for distributional forecasts) of $h$-day forward returns on the grid; choose the penalty by walk-forward validation.
4. Read importance by summed absolute coefficients across type/horizon/side; expect percentile/min/max levels at medium horizons to dominate and volume features to drop.

**Algorithm 6 — State-conditional moment tables (F37).**
1. Discretize the state coarsely enough that each cell has hundreds of observations after pooling within liquidity buckets.
2. Sweep the tape once, accumulating per-cell counts and sums for: move indicator at $\delta$, move size, move size at first change, time to first change.
3. At prediction, average over $k$ nearest states, treating opposite-sign states as infinitely distant.
4. Predict two-stage: move vs. no-move against a threshold, then the sign of the conditional mean.

**Algorithm 7 — Pool-level factor combination (mining-style).**
1. Maintain a factor pool with weights. For each candidate, tentatively add it and re-optimize the linear-combination weights against the target (rank-IC of the combined score with forward returns).
2. Admit only if the **pool** objective improves net of a redundancy penalty (cap pairwise correlations or penalize weight collinearity).
3. Periodically prune factors whose removal does not degrade the pool objective.
4. Freeze weights on a schedule; evaluate strictly walk-forward, cross-sectionally within buckets.

**Algorithm 8 — Liquid-to-illiquid propagation (F18).**
1. Map every bond to its issuer curve; anchor = most liquid sibling by trailing print count.
2. Compute all factors on the anchor; assign to illiquid siblings, optionally decayed by maturity gap.
3. Also compute each sibling's basis to the anchor-implied curve value; use the basis as a convergence factor.
4. Never propagate in reverse (illiquid-estimated models onto liquid bonds) — the generalization is empirically asymmetric.

---

## 14. Source map

| Source (as read) | Tag | Factors drawn |
|---|---|---|
| Lehalle & Neuman, *Incorporating signals into optimal trading* | LN | F6 (imbalance as OU signal) |
| Muni Toke & Yoshida, *Ratios of Cox-type intensities* | MTY20 | F1, F2, F35 |
| Muni Toke & Yoshida, *Marked point processes and intensity ratios* | MTY22 | F4, F35, F36 |
| Palguna & Pollak, *Mid-price prediction in a LOB* | PP16 | F8, F23, F37; share-imbalance variant of F6 |
| Li et al., *Intelligent market making* | LDZ14 | F7; VPIN pointer (F33) |
| Cartea, Duran-Martin & Sánchez-Betancourt, *Detecting toxic flow* | CDS | F24, F31, F32; the clock grid |
| Cartea & Sánchez-Betancourt, *A simple strategy to deal with toxic flow* | CSB | F34 (informed/uninformed decomposition) |
| Bank, Cartea & Körber, *Optimal execution and speculation with trade signals* | BCK | F3 (flow-driven prices; liquidity state) |
| Webster (chapter), *Mathematical models of price impact* | OW/W | F13 (propagator; impact–alpha myopia) |
| Yu et al., *OrderFusion* | OF | F5, F22 (side separation) |
| Yu et al., *Orderbook feature learning* (electricity) | OFL | F15–F18; Algorithm 5; asymmetric generalization |
| Yu, Xue, Ao et al., *AlphaGen* (KDD'23) | AG | operator grammar; Algorithm 7 |
| Ren et al., *RiskMiner* | RM | operand/operator inventory |
| Wang et al., *FactorMiner* | FM | F9–F12, F14, F19–F21, F25–F30, §12 expressions |
| Yu, Xue, Ao & He, *LLM-assisted alpha discovery* | LLM | grammar validation conventions |

**Exclusions.** Quote-placement and dealing-strategy mathematics (optimal spreads, inventory controls, HJB systems), execution-scheduling solutions, and broker internalization/externalization policies are out of scope; only the predictive state variables inside those frameworks were retained.
