# Multi-Clock Feature Engine

This stage adds reusable point-in-time state machinery only.

It does not add predictive factors.
It does not fit models.
It does not change source-field economics.

## Core Contract

The engine consumes `MarketEvent` records.

Each event preserves:

- source event time: `timestamp`
- receive time: `receive_time`
- effective time: `effective_time`
- publication time: `publication_time`
- revision time: `revision_time`
- feature calculation time: `feature_time`

The default as-of inclusion policy is `effective_time`.

For late-published sources such as TRACE, use `timestamp_policy="publication"` when a feature must respect public dissemination time.

## Supported Clocks

The engine supports independent clocks.

| Clock | Purpose |
| --- | --- |
| `calendar` | elapsed business time windows, such as 5 minutes, 30 minutes, 2 hours, 1 business day, and 5 business days |
| `rfq_event` | last N RFQ events |
| `trade_event` | last N TRACE or executed RFQ trades |
| `notional` | newest events until cumulative absolute notional reaches a threshold |
| `composite_update` | last N meaningful composite snapshots |

Calendar windows skip weekends and configured holidays.

## Point-In-Time Rules

All windows close at the requested `as_of` timestamp.

No event with an as-of timestamp after `as_of` enters the state.

Corrections and cancellations apply only after their own as-of timestamp.

This prevents a later composite revision from rewriting an earlier historical state.

Duplicate handling is explicit:

- `keep_first`
- `keep_last`
- `reject`

Out-of-order handling is explicit:

- `sort`
- `reject`

## Output Shape

Every state output includes:

- `value`
- `observation_count`
- `effective_sample_size`
- `last_observation_time`
- `staleness_seconds`
- `quality_flags`

`value=None` means no valid estimate exists.

It is not the same as zero.

Common flags include:

- `no_observations`
- `missing_value`
- `missing_side`
- `insufficient_observations`
- `stale`
- `outside_universe`

## Operators

The operator module provides typed statistics.

| Operator | Meaning |
| --- | --- |
| `count` | number of observations |
| `signed_count` | sum of valid `+1/-1` sides |
| `sum` | sum of numeric values |
| `signed_sum` | sum of `side * value` |
| `mean` | arithmetic mean |
| `weighted_mean` | positive-weight weighted mean |
| `vwap` | weighted mean using price and notional |
| `min` | minimum |
| `max` | maximum |
| `first` | first valid value |
| `last` | last valid value |
| `percentile` | configurable percentile |
| `std` | sample standard deviation |
| `mad` | median absolute deviation |
| `ewma` | elapsed-time EWMA |
| `run_length` | signed same-side run length |
| `time_since_last_event` | seconds since the newest observation |
| `intensity` | count divided by window seconds |
| `robust_slope` | Theil-Sen style median pairwise slope |
| `robust_covariance` | median centered product |
| `robust_correlation` | robust covariance scaled by median absolute deviations |
| `rolling_rank` | rank of latest value inside its own window |
| `cross_sectional_rank` | rank across a supplied cross-section |
| `time_of_day_zscore` | value relative to supplied time-of-day baseline |
| `residual` | observed value minus supplied as-of prediction |

Aggregate scopes are explicit.

Supported scopes are:

- bond
- issuer
- sector
- rating
- market

## Example

Run:

```bash
cd bond_alpha
python examples/state_engine_replay.py
```

The example replays one RFQ, one TRACE trade, and one composite update for one bond.

It prints a tidy state table.

## Testing Coverage

The synthetic tests cover:

- simultaneous RFQs
- no observations versus zero values
- duplicate messages
- cancellation and correction messages
- late TRACE reports
- composite revisions
- crossing midnight
- holidays
- bonds entering and leaving the universe
- identical batch and streaming outputs

The parity test is the main guardrail.

Batch replay and online replay must produce the same state for the same event set and as-of times.
