# Synthetic Truth

Simulator version: `0.1.0`

Scenario: `leadlag_only`

Config hash: `fa92951b3a4c12b56e4931b143ed26fa919d13708d3be31e2df419f676a91d3c`

## Data And Units

- Side semantics: BUY=+1, SELL=-1 using TRACE rpt_side_cd mapping
- Price units: par-price points; 100 means par and 0.01 means one cent
- Notional units: TRACE entrd_vol_qt treated as par quantity
- Public data and truth data are physically separate.

## SynthCity And Marks

- Selected mark model: `empirical_fallback`
- SynthCity version: `importable_but_registry_failed`
- Available plugins: `[]`
- Failure recorded: `registry failed: AttributeError: module 'torch.nn' has no attribute 'RMSNorm'; arf: plugin not available in installed SynthCity registry`

## Liquidity

- Realized median events per bond-session: `2.070767`
- Realized p10 events per bond-session: `0.532937`
- Realized max events per bond-session: `25.588624`

## Hawkes Clock

- Same-side mass: `0.1`
- Opposite-side mass: `0.1`
- Leader-follower mass: `0.03`
- Half-lives in minutes: `(5.0, 30.0, 120.0)`
- Spectral radius: `0.20000000033354393`

## Controlled Effects

- Large-print reversal: state jump side * A * sqrt(q/q90), A=0.08, half-life=0.5 trading day
- Sign persistence: own same-side branching mass exceeds opposite-side mass in controlled scenarios
- Leader-follower lead-lag: issuer leader events add side * 0.05 price points to illiquid follower leadlag state

## Null Definition

removes incremental large-print reversal, symmetrizes own excitation, and disables leader-follower price response

## Known Limitations

- Rating, maturity, sector, duration, OAS, bid, ask, and vendor fair value were not available in local TRACE.
- Fair value uses a transaction-price proxy route in this vertical slice.
- The empirical fallback is selected because the installed SynthCity registry fails in this environment.
- No differential-privacy claim is made.
