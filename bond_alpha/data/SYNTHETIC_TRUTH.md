# Synthetic Truth

Simulator version: `0.1.0`

Scenario: `controlled_null`

Config hash: `05d3d74c214db0a473b5063532651da6e756be7e2bbe70866fc35318a109cf55`

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

- Realized median events per bond-session: `1.952381`
- Realized p10 events per bond-session: `0.420635`
- Realized max events per bond-session: `25.955026`

## Hawkes Clock

- Same-side mass: `0.1`
- Opposite-side mass: `0.1`
- Leader-follower mass: `0.0`
- Half-lives in minutes: `(5.0, 30.0, 120.0)`
- Spectral radius: `0.2`

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
