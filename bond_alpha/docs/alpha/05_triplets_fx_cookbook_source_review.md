# Triplets And FX Cookbook Source Review

Source: `triplets_and_fx_cookbook_standalone_algorithms.md`

This checkpoint maps the source methods into the existing MechanicalAlpha architecture.
It is intentionally conservative. Source-literal FX methods remain blocked when the
current corporate-bond public bundle lacks the required point-in-time inputs.

## Mapping Table

| source object | formal equation | existing code that can be reused | target module | target interface | required inputs | available inputs | missing inputs | corporate-bond mapping | implementation disposition | tests required | blocking decisions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar clock | `tau_k = t0 + k * delta` | `AlphaInputBundle.events.prediction_timestamp` | `mechanical_alpha.triplets.clocks` | `build_calendar_clock(...) -> ClockIndex` | timestamps, frequency | event timestamps | holiday calendar optional | sample bond states on fixed physical time | NEW_CORE_OPERATOR | fixed interval, future mutation | none |
| event clock | `tau_k = inf{t: N(t)-N(tau_{k-1}) >= n}` | `alpha_common.prior`, events table | `mechanical_alpha.triplets.clocks` | `build_event_clock(...) -> ClockIndex` | event timestamps, threshold | canonical events/RFQs | event class filters optional | stop after N observable events | NEW_CORE_OPERATOR | monotonicity, duplicate timestamps | none |
| information clock | `A(tau_k)-A(tau_{k-1}) >= a` | canonical events with notional | `mechanical_alpha.triplets.clocks` | `build_information_clock(...) -> ClockIndex` | nonnegative activity scores | notional, count proxy | spread-volume information optional | adapted activity clock using nonnegative event information | NEW_CORE_OPERATOR | nonnegative, adapted clock | none |
| triplet-panel construction | `(x_t-x_{t-L}, y_{t+H}-y_t)` | `AlphaInputBundle`, fair-value optional table | `mechanical_alpha.triplets.panel` | `build_triplet_panel(...) -> DataFrame` | sampled state, lag, anchor, horizon | price, optional fair_value/oas/duration | residual model optional | clean-price, spread-implied, residual targets where available | NEW_CORE_OPERATOR | trend/reversal fixtures, spread sign | none |
| triplet estimation | `rho = Spearman(past, future)` | scipy allowed by project | `mechanical_alpha.triplets.inference` | `estimate_triplet_family(...)` | triplet panel | computed panel | cluster bootstrap optional | dependence-aware Spearman baseline with group columns retained | NEW_CORE_OPERATOR | strict trend, alternating reversal | none |
| multiplicity adjustment | Holm/BH over searched family | none | `mechanical_alpha.triplets.inference` | `adjust_triplet_multiplicity(...)` | p-values, method | p-values | none | all searched candidates included | NEW_CORE_OPERATOR | rejected candidates included | none |
| triplet selection | `selected = q <= alpha, n >= min_n` | none | `mechanical_alpha.triplets.inference` | `select_triplets(...)` | adjusted estimates | estimates | none | train-only selection artifact | NEW_CORE_OPERATOR | train-only freeze | none |
| triplet scoring | `z = Phi^{-1}(rank(past)) * sign(rho)` | `operators.cross_sectional_rank` concept | `mechanical_alpha.triplets.signal` | `score_triplet(...)` | frozen rank transform, selected triplets | price/fair-value panels | residual targets optional | positive means positive expected future return | NEW_CORE_OPERATOR | frozen rank, future mutation | none |
| signal aggregation | `S = sum_j w_j z_j / sum_j |w_j|` | none | `mechanical_alpha.triplets.signal` | `aggregate_triplet_signals(...)` | component scores, weights | component scores | none | aggregate selected components only | NEW_CORE_OPERATOR | zero weights, missing components | none |
| matched-clock evaluation | compare triplet clock with calendar control | existing reports concept only | `mechanical_alpha.triplets.evaluation` | `evaluate_clock_transfer(...)` | scores, forward returns, controls | score panels | full runner integration | diagnostic table for clock transfer | NEW_CORE_OPERATOR | matched opportunity counts | none |
| inverse-volatility sign weights | `w_i = sign(s_i)/sigma_i` normalized | none | `mechanical_alpha.fx_cookbook.common` | `inverse_volatility_sign_weights(...)` | signals, volatility | signal/vol inputs | none | reusable portfolio primitive | NEW_CORE_OPERATOR | zero vol, gross exposure | none |
| signal-proportional weights | `w_i = s_i/sigma_i^p` normalized | none | `mechanical_alpha.fx_cookbook.common` | `signal_proportional_weights(...)` | signals, volatility | signal/vol inputs | none | reusable portfolio primitive | NEW_CORE_OPERATOR | zero denominator | none |
| equal-weight rank halves | long top half, short bottom half | none | `mechanical_alpha.fx_cookbook.common` | `equal_weight_rank_halves(...)` | signals | signals | none | cross-sectional bond portfolio primitive | NEW_CORE_OPERATOR | ties, small universe | none |
| linear-rank halves | weights proportional to centered ranks | none | `mechanical_alpha.fx_cookbook.common` | `linear_rank_halves(...)` | signals | signals | none | cross-sectional bond portfolio primitive | NEW_CORE_OPERATOR | neutrality, normalization | none |
| beta-neutral projection | `w* = w - beta (beta'w)/(beta'beta)` | none | `mechanical_alpha.fx_cookbook.common` | `project_beta_neutral(...)` | weights, beta | optional risk input | beta estimates optional | portfolio post-processing only | NEW_CORE_OPERATOR | beta exposure zero | none |
| position bounds | `lower_i <= w_i <= upper_i` | none | `mechanical_alpha.fx_cookbook.common` | `apply_position_bounds(...)` | weights, bounds | weights | ADV optional | reusable bound primitive | NEW_CORE_OPERATOR | caps, gross normalization | none |
| tranche rebalancing | average active tranche target weights | none | `mechanical_alpha.fx_cookbook.common` | `tranche_rebalance(...)` | target weights, tranche count | weights | calendar optional | deterministic turnover smoother | NEW_CORE_OPERATOR | tranche accounting | none |
| Price Momentum | `s_i = r_i(t-L,t)` | price/fair-value tables | `mechanical_alpha.fx_cookbook.momentum` | `compute_total_return_momentum_signal(...)` | returns, lookback, denominator | price/fair_value optional | total-return coupon data optional | clean-price/FV/residual momentum adapter | EXTEND_EXISTING | continuation fixture, blocked variants | `MOM-001`, `MOM-002` |
| Carry | approximate `carry = fwd/spot - 1` | duration/coupon fields optional | `mechanical_alpha.fx_cookbook.carry` | `compute_fx_carry(...)`, `blocked_strategy(...)` | FX forwards, funding, quote orientation | coupon/duration optional only | FX forwards, financing curve | blocked source-literal; bond adapter requires PI curve definition | BLOCKED_HUMAN_DECISION | blocked status | `CARRY-001`, `CARRY-002`, `CARRY-003` |
| Fundamental Value | value gap to DOLS REER fair value | none | `mechanical_alpha.fx_cookbook.value` | `blocked_strategy(...)` | REER, PPP/fundamentals | none | REER/fundamental panels | blocked source-literal | BLOCKED_HUMAN_DECISION | blocked status | `VALUE-001` |
| Rates Momentum Spill-Over | standardized rate differential momentum | external_factors optional | `mechanical_alpha.fx_cookbook.rates_momentum_spillover` | `compute_rates_momentum_spillover(...)` | PIT rates/curve changes | external_factors if supplied | no guaranteed PIT rates | generic adapter; blocked without rate factors | BLOCKED_MISSING_DATA | missing data failure | none |
| COFFEE/DTCC positioning | options call-put notional imbalance | none | `mechanical_alpha.fx_cookbook.coffee` | `blocked_strategy(...)` | options positioning | none | DTCC/COFFEE fields | unavailable in current bond bundle | BLOCKED_MISSING_DATA | blocked status | `COFFEE-001`, `COFFEE-002` |
| CFTC continuation | `position_ratio_4w` continuation | none | `mechanical_alpha.fx_cookbook.cftc_continuation` | `blocked_strategy(...)` | COT reports | none | CFTC data | unavailable in current bond bundle | BLOCKED_MISSING_DATA | blocked status | none |
| CFTC reversal | z-score net positions reversal | none | `mechanical_alpha.fx_cookbook.cftc_reversal` | `blocked_strategy(...)` | COT reports, reversal convention | none | CFTC data | unavailable in current bond bundle | BLOCKED_HUMAN_DECISION | blocked status | `CFTC-R-001` |

## Source-Review Checkpoint

No duplicate pipeline is introduced.
The implementation extends the existing `mechanical_alpha` package and registry.
The simulator truth directories and Gate 4 quarantined outputs are not read.
Source-literal FX strategies with unresolved data or PI decisions are represented as typed blocked strategies.

