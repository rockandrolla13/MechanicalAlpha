# Alpha Implementation Audit And Hardening

Date: 2026-09-01

Scope inspected:

- root repository docs: `AGENTS.md`, `CLAUDE.md`, `docs/alpha/*`, `config/alpha/*`
- simulator and alpha prompts: `gate4_alpha_factory_master_prompt.md`, `SYNTHETIC_SIMULATOR_MASTER_PROMPT.md`, `bond_alpha/docs/GATE3_PROMPT.md`
- cookbook source: `triplets_and_fx_cookbook_standalone_algorithms.md`
- portable alpha code: `bond_alpha/src/mechanical_alpha/**`
- Alpha Factory code: `bond_alpha/src/bondalpha/**`
- tests: `bond_alpha/tests/**`
- frozen alpha spec: `bond_alpha/models/alpha_frozen/alpha-spec-201e04afa128`
- reports: `bond_alpha/reports/alpha/**`, `bond_alpha/reports/gate3/**`, `bond_alpha/reports/alpha_gate4/**`

## Source-Of-Truth Notes

There are two active alpha surfaces:

1. `mechanical_alpha`: portable standalone alpha files over `AlphaInputBundle`.
2. `bondalpha`: Alpha Factory v1 used for Gate 3/Gate 4 research, freeze, and blinded evaluation.

The implementation evidence does not support treating every registry row as implemented.
`mechanical_alpha.registry.ALPHA_SPECS` includes A1-A16 and B1-B15 capability declarations, but only A1, A2, A3, A4, A5, A6, A16, and T1 have standalone compute implementations.

## Inventory

| canonical_alpha_id | repository_aliases | registry_entry | implementation_files | primary_functions | specs/reports/tests | bond support | ETF support | status | correctness and validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `A1` | RFQ count imbalance | `mechanical_alpha.registry.ALPHA_INDEX` | `src/mechanical_alpha/alphas/A1_rfq_count_imbalance.py`, wrapper in `features/microstructure.py` | `describe`, `compute`, `add_features` | `config/alpha/feature_registry.yaml`, `docs/alpha/03_rfq_flow_features.md`, `tests/test_standalone_alpha_files.py`, `tests/test_microstructure_features.py` | yes, if side is valid | no dedicated ETF adapter | implemented | Tested with hand calculations. Corporate-bond sign depends on source side validation. |
| `A2` | RFQ notional imbalance | same | `src/mechanical_alpha/alphas/A2_rfq_notional_imbalance.py` | `compute`, `add_features` | same tests | yes, if side/notional are valid | no dedicated ETF adapter | implemented | Tested. The as-of cap claim in config says caps use rows inside the window; code does that in `transform_notional` on the historical window. |
| `A3` | buy/sell intensity pressure | same | `src/mechanical_alpha/alphas/A3_buy_sell_intensity.py` | `compute`, `add_features` | smoke/import tests | yes, if side is valid | no dedicated ETF adapter | implemented | Basic validation only. Needs stronger elapsed-time EWMA fixture tests. |
| `A4` | last-side persistence | same | `src/mechanical_alpha/alphas/A4_last_side_persistence.py` | `compute`, `add_features` | hand-calculation tests | yes, if side is valid | no dedicated ETF adapter | implemented | Tested for last side, run length, and switching hazard. |
| `A5` | activity surprise | same | `src/mechanical_alpha/alphas/A5_activity_surprise.py` | `compute`, `add_features` | registry/diagnostic tests | yes | possible with ETF event adapter, not implemented | partially implemented | Corporate-bond TRACE/RFQ activity only. ETF order-book activity is not wired into the portable bundle. |
| `A6` | spread-conditioned flow pressure | same | `src/mechanical_alpha/alphas/A6_spread_conditioned_flow.py` | `compute`, `add_features` | optional-field tests | yes when quotes/spreads exist | no dedicated ETF adapter | implemented with optional degradation | Point-in-time quote lookup is tested. Real bond quote coverage remains data-dependent. |
| `A16` | RFQ scarcity and disagreement | same | `src/mechanical_alpha/alphas/A16_rfq_scarcity_disagreement.py` | `compute`, `add_features` | optional-field tests | yes when RFQ table exists | not applicable | implemented with optional degradation | Works for RFQ data. TRACE-only data degrades. |
| `T1` | triplet clock momentum/reversal | `T1` in `mechanical_alpha.registry` | `src/mechanical_alpha/alphas/T1_triplet_momentum_reversal.py`, `src/mechanical_alpha/triplets/*` | `fit_triplet_method`, `score_triplet_method`, `compute` | `docs/alpha/05_triplets_fx_cookbook_source_review.md`, `tests/test_triplets_fx_cookbook.py` | yes with price or fair-value proxy | possible only if ETF prices are adapted into `AlphaInputBundle`; no ETF adapter now | implemented, early | Tests cover continuation, spread sign, multiplicity, and future-mutation fixture. It is not yet validated on real or Gate 4 data. |
| `FX_MOM` | price momentum cookbook | `FX_MOM` | `src/mechanical_alpha/fx_cookbook/momentum.py` | `compute_total_return_momentum_signal`, weight builders | `tests/test_triplets_fx_cookbook.py` | component only | component only | component implemented | Not a complete alpha. It provides source-literal math. MOM-001/MOM-002 remain open for literal strategy release. |
| `FX_CARRY` | carry, carry roll-down | `FX_CARRY` | `src/mechanical_alpha/fx_cookbook/carry.py` | `compute_fx_carry`, `blocked_carry` | `tests/test_triplets_fx_cookbook.py` | blocked | blocked | blocked human decision | Needs CARRY-001/CARRY-002/CARRY-003 and point-in-time curve/financing data. |
| `FX_VALUE` | fundamental value, fundamental relative value | `FX_VALUE` | `src/mechanical_alpha/fx_cookbook/value.py` | `blocked_fundamental_value` | blocker tests indirectly via registry/docs | blocked | blocked | blocked human decision | Distinct from issuer-relative value. Requires REER/fundamental panels. |
| `RATES_SPILLOVER` | rates momentum spill-over, rates-credit spillover | `RATES_SPILLOVER` | `src/mechanical_alpha/fx_cookbook/rates_momentum_spillover.py` | `compute_rates_momentum_spillover`, `blocked_rates_spillover` | `docs/alpha/05_triplets_fx_cookbook_source_review.md` | blocked unless PIT rates exist | possible for bond ETF if rates adapter exists | blocked missing data | No canonical PIT rates/curve factors are guaranteed in current alpha bundle. |
| `COFFEE_DTCC` | options positioning | `COFFEE_DTCC` | `src/mechanical_alpha/fx_cookbook/coffee.py` | `blocked_coffee_dtcc` | blocker tests | blocked | blocked | blocked missing data | No DTCC/COFFEE options positioning channel. |
| `CFTC_CONT` | futures positioning continuation | `CFTC_CONT` | `src/mechanical_alpha/fx_cookbook/cftc_continuation.py` | `blocked_cftc_continuation` | blocker docs | blocked | blocked | blocked missing data | No CFTC COT channel. |
| `CFTC_REV` | futures positioning reversal | `CFTC_REV` | `src/mechanical_alpha/fx_cookbook/cftc_reversal.py` | `blocked_cftc_reversal` | blocker tests | blocked | blocked | blocked human decision | CFTC-R-001 remains open and no COT data exist. |
| `large_print_reversal` | `reversal_pressure`, Alpha Factory reversal | `configs/alphas/reversal.yaml`, frozen `feature_manifest.json` | `src/bondalpha/features/reversal.py`, `src/bondalpha/reversal/family.py` | `compute`, `build_reversal_family` | `reports/alpha/gate3/reversal.md`, `models/alpha_frozen/alpha-spec-201e04afa128` | yes on synthetic public bond data | no dedicated ETF path | implemented but leaky | `features/reversal.py:13-14` uses full-sample median and p90 by scenario/bond. That leaks future notional thresholds into historical features. |
| `own_flow_persistence` | `flow_persistence`, `last_side`, `same_side_run_length` | `configs/alphas/flow_persistence.yaml`, frozen manifest | `src/bondalpha/features/flow_persistence.py`, `src/bondalpha/flow/family.py` | `compute`, `build_flow_persistence_family` | Gate 3 reports and smoke tests | yes on synthetic public bond data | no dedicated ETF path | implemented but leaky | `features/flow_persistence.py:14-16` rolling counts include the current event side. `_same_side_run` also includes current side. For pre-event prediction this leaks the label event. |
| `issuer_leader_follower` | `leader_follower_pressure`, `issuer_leadlag` | `configs/alphas/leader_follower.yaml`, frozen manifest | `src/bondalpha/features/leader_follower.py`, `src/bondalpha/leadlag/family.py` | `compute`, `build_lead_lag_family` | `reports/alpha/gate3/leadlag.md`, new hardening tests | yes on synthetic public bond data | no dedicated ETF path | hardened | Pre-hardening code selected leaders from full-sample activity and rolled issuer flow by row order. Current code uses prior-only leader activity and prior-only leader flow. |
| `issuer_relative_value` | `relative_value_gap` | `configs/alphas/relative_value.yaml`, frozen manifest | `src/bondalpha/features/relative_value.py`, `src/bondalpha/relative_value/family.py` | `compute`, `build_relative_value_family` | Gate 3 reports and smoke tests | yes on synthetic public bond data | no dedicated ETF path | implemented but leaky | `features/relative_value.py:11-14` uses current price diff and full-scenario robust z-score. `relative_value/family.py` computes group medians over all rows supplied. |
| `alpha_factory_composite` | composite | `configs/alphas/composite.yaml` | `src/bondalpha/composite/selection.py` | `build_composite_scaffold` | `tests/alpha/test_alpha_family_outputs.py` | synthetic public bond data only | no dedicated ETF path | partial | Combines available family outputs. It inherits weaknesses of component signals. |
| `liquidity_control` | log liquidity control | frozen manifest | `src/bondalpha/features/controls.py` | `compute` | Alpha Factory tests | synthetic public bond data | no dedicated ETF path | control, leaky | `features/controls.py:11` uses full-sample event count as a feature. This is acceptable only if treated as an ex-post dataset descriptor, not an as-of alpha feature. |
| `B1-B15` | bond_alpha_factors.md family | `mechanical_alpha.registry.ALPHA_SPECS` only | no standalone compute files for B1-B15 | none | `docs/alpha/00_factor_capability_matrix.md` | varies | some ETF concepts possible | mostly unimplemented declarations | Capability declarations exist. Production formulas are not implemented except where A-family microstructure overlaps. |
| `A7-A15` | older QuantCraft alpha family ids | `mechanical_alpha.registry.ALPHA_SPECS` only | no standalone compute files for A7-A15 | none | `docs/alpha/00_factor_capability_matrix.md` | mostly blocked or partial | no ETF implementation | unimplemented declarations | Registry specs are availability declarations, not implementations. |

## Weakest Substantive Alpha Selected For Hardening

Selected alpha: `issuer_leader_follower` / `leader_follower_pressure`.

Reason:

- It had a substantive implementation used by Alpha Factory.
- It was economically central because Gate 3 includes a lead-lag positive control.
- It was the weakest point-in-time implementation: pre-hardening code selected the issuer leader using full-sample activity and applied rolling issuer flow by row order.
- It affected the frozen Alpha Factory feature set.

Hardened behavior:

- `src/bondalpha/features/leader_follower.py` now sorts by scenario, issuer, timestamp, and event id.
- The leader for each event row is selected from prior observed issuer activity only.
- Leader rows receive zero signal.
- Follower rows receive a decayed, normalized signed pressure from prior leader events only.
- Future appended events cannot alter historical lead-lag signals.
- Input row order cannot alter signals.

Validation added:

- `tests/alpha/test_leader_follower_hardening.py::test_leader_follower_uses_prior_leader_activity_only`
- `tests/alpha/test_leader_follower_hardening.py::test_future_events_do_not_change_historical_leadlag_signal`
- `tests/alpha/test_leader_follower_hardening.py::test_leader_follower_is_time_ordered_not_input_ordered`

## Most Important Open Issues

1. `large_print_reversal` still uses full-sample notional median and p90 thresholds.
2. `own_flow_persistence` rolling counts include the current event side.
3. `issuer_relative_value` uses full-sample scenario scaling and same-row price changes.
4. `liquidity_control` uses full-sample event counts.
5. `target_labels.future_issuer_residual_move_*` uses issuer row shift rather than an as-of issuer fair-value or mean move.
6. Bond ETF support is not implemented as a first-class alpha path.
7. Source-literal FX carry, value, positioning, and CFTC strategies are correctly blocked.
8. A7-A15 and B1-B15 are mostly capability declarations, not implemented alphas.
9. Frozen alpha spec `alpha-spec-201e04afa128` predates the current hardening and should not be treated as including the hardened lead-lag behavior until refrozen in a new version.
10. Gate 3/Gate 4 reports validate workflows and some positive controls, but they do not yet validate each individual alpha family with robust ablations.
