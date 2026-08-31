# Repository And Data Audit

Date: 2026-08-30

Scope: audit only. No production factor, model, or backtest code was added.

## Sources Read

- `AGENTS.md`
- `CLAUDE.md`
- `event_table.md`
- `anonymous_rfq_alpha_feature_research_spec_from_quantcraft.md`
- `bond_alpha_factors.md`
- `bond_alpha/README.md`
- `bond_alpha/pyproject.toml`
- `bond_alpha/bond_alpha/data/acquire.py`
- `bond_alpha/src/bondsim/*`
- `bond_alpha/tests/*`
- existing reports under `bond_alpha/reports/`
- local read-only `marketdb`

## Blueprint

The audit separates four things:

- what the repo can already do
- what marketdb actually contains
- what alpha factors can be built from those fields
- what must be validated before production research

## Ideation Summary

Two approaches were considered.

| Approach | Description | Main Risk | Decision |
| --- | --- | --- | --- |
| TRACE-first audit | Treat `marketdb.trace` as the only confirmed bond print source. | It underuses possible RFQ/composite data if it exists elsewhere. | Selected. It avoids invented fields. |
| Broad-source audit | Assume RFQ, evaluated marks, curves, and composites exist somewhere. | High leakage and false availability risk. | Rejected for this audit. |

## Design Summary

The audit outputs are plain docs and one YAML draft.

No model code is changed.

No factor code is added.

No raw data is modified.

## Repository Map

| Area | Current State | Evidence | Notes |
| --- | --- | --- | --- |
| ingestion | Partial. `bond_alpha.data.acquire.load_tape` supports WRDS stub, FINRA public CSV, and synthetic. `bondsim` can inspect marketdb. | `bond_alpha/bond_alpha/data/acquire.py`, `bond_alpha/src/bondsim/discovery.py` | Real marketdb ingestion is in `bondsim.preprocess`, not the older `bond_alpha.data.acquire` interface. |
| normalization | Partial. `bondsim.preprocess` writes processed bonds/events parquet. | `bond_alpha/src/bondsim/preprocess.py` | Side convention differs between specs and simulator notes. Must be resolved before factors. |
| feature calculation | Not implemented. | `bond_alpha/bond_alpha/factors/__init__.py` only. | This is correct for the audit stage. |
| fair value | Prototype only. Simulator uses transaction-price proxy. | `bond_alpha/src/bondsim/prices/engine.py`, `reports/price_model_fit.md` | No vendor fair value, OAS curve, or composite mid is confirmed. |
| model training | Not implemented for alpha factors. Simulator has a mark-model adapter and empirical fallback. | `bond_alpha/src/bondsim/marks/*` | SynthCity registry currently fails in this env. |
| replay/backtest | Not implemented for alpha factors. | no backtest package found | Needed after data contract is locked. |
| RFQ response | Not implemented. | no RFQ response module found | Project instructions say this is not the primary objective. |
| logging and monitoring | Minimal. CLI writes reports and manifests. | `bond_alpha/src/bondsim/pipeline.py`, `bond_alpha/reports/*` | No production logging framework yet. |

## Data Inventory

### `marketdb.trace`

| Field | Value |
| --- | --- |
| table or stream | `trace` |
| inferred type | TRACE executions / public-or-enhanced prints |
| primary key | no declared key. Candidate key: `cusip, trd_exctn_ts, rptd_pr, entrd_vol_qt, rpt_side_cd, cntra_mp_id` |
| event timestamp | `trd_exctn_ts` |
| receive timestamp | unavailable |
| publication timestamp | unavailable at intraday precision |
| revision timestamp | unavailable |
| reporting date | `trd_rpt_dt` |
| frequency | event tape |
| history coverage | 2023-05-30 00:03:11 to 2025-09-30 17:43:45 |
| rows | 7,209,827 |
| bonds | 22,682 CUSIPs |
| issuers | 15 non-null `company_symbol` values |
| expected latency | ambiguous. Only `trd_rpt_dt` is present, not dissemination time |
| side convention | `rpt_side_cd` has `B` and `S`; perspective is ambiguous |
| size units | `entrd_vol_qt`; warehouse does not record units |
| price units | `rptd_pr`; treated as par price where 100 means par |
| missingness | issuer missing in 268 rows; key model fields have 0 nulls in the audit query |
| duplicates | approximate key distinct count 6,041,392 vs 7,209,827 rows |
| point-in-time safety | partial. Trade timestamp is usable. Publication and revision timing are not proven |

Issuer panel:

| Issuer | Rows | CUSIPs | First Date | Last Date |
| --- | ---: | ---: | --- | --- |
| JPM | 3,361,011 | 22,313 | 2023-05-30 | 2025-09-30 |
| AAPL | 927,738 | 57 | 2023-05-30 | 2025-09-30 |
| INTC | 653,948 | 41 | 2023-05-30 | 2025-09-30 |
| AMZN | 615,033 | 36 | 2023-05-30 | 2025-09-30 |
| MSFT | 422,173 | 39 | 2023-05-30 | 2025-09-30 |
| PEP | 300,367 | 62 | 2023-05-30 | 2025-09-30 |
| IBM | 196,695 | 46 | 2023-05-30 | 2025-09-30 |
| CSCO | 196,409 | 19 | 2023-05-30 | 2025-09-30 |
| GOOG | 140,187 | 13 | 2023-05-30 | 2025-09-30 |
| CMCS | 133,725 | 19 | 2023-05-30 | 2025-09-30 |
| COST | 97,463 | 5 | 2023-05-30 | 2025-09-30 |
| NVDA | 96,125 | 9 | 2023-05-30 | 2025-09-30 |
| RIG | 61,371 | 17 | 2023-05-30 | 2025-09-30 |
| VBLF | 7,117 | 1 | 2023-05-30 | 2025-09-30 |
| MS | 197 | 5 | 2023-05-30 | 2025-09-25 |

Side / contra-party distribution:

| `rpt_side_cd` | `cntra_mp_id` | Rows |
| --- | --- | ---: |
| S | C | 2,039,262 |
| S | D | 1,838,899 |
| B | D | 1,660,159 |
| B | C | 1,014,801 |
| S | A | 227,802 |
| B | T | 161,965 |
| S | T | 153,884 |
| B | A | 113,055 |

Audit note: `cntra_mp_id='D' AND rpt_side_cd='B'` is a likely interdealer double-report leg.
It affects 1,660,159 rows.
Counts, volume, and flow features must define whether this leg is kept or filtered.

### `marketdb.bond_link`

| Field | Value |
| --- | --- |
| table or stream | `bond_link` |
| inferred type | CUSIP to CRSP equity link |
| primary key | candidate: `cusip, permno, trace_startdt, trace_enddt` |
| event timestamp | none |
| receive timestamp | unavailable |
| publication timestamp | unavailable |
| revision timestamp | unavailable |
| frequency | reference table |
| history coverage | date windows via `trace_startdt, trace_enddt` |
| rows | 53,785 |
| side convention | not applicable |
| size units | not applicable |
| price units | not applicable |
| missingness | not fully profiled |
| point-in-time safety | partial. Link date windows exist, but backfill timing is not known |

### `marketdb.bond_to_equity`

| Field | Value |
| --- | --- |
| table or stream | `bond_to_equity` |
| inferred type | TRACE joined to equity names |
| primary key | inherits TRACE candidate key plus `permno` |
| event timestamp | `trd_exctn_ts` |
| receive timestamp | unavailable |
| publication timestamp | unavailable |
| revision timestamp | unavailable |
| frequency | event tape view |
| history coverage | 2023-05-30 to 2025-09-30 |
| rows | 7,094,903 |
| bonds | 22,376 CUSIPs |
| tickers | 13 |
| point-in-time safety | partial. `name_extrapolated` exists and must be handled explicitly |

Audit note: the marketdb skill warns that the equity-link view drops after 2024-12-31 under strict CRSP name windows.
Use `trace.company_symbol` for issuer grouping unless equity data is specifically needed.

### `marketdb.crsp_daily`

| Field | Value |
| --- | --- |
| table or stream | `crsp_daily` |
| inferred type | daily equity prices and returns |
| primary key | candidate: `permno, date` |
| event timestamp | `date` |
| receive timestamp | unavailable |
| publication timestamp | unavailable |
| revision timestamp | unavailable |
| frequency | daily |
| history coverage | 2019-01-02 to 2021-12-31 |
| rows | 22,710 |
| permnos | 30 |
| fields | `prc, openprc, bidlo, askhi, bid, ask, vol, ret, shrout, cfacpr, cfacshr, numtrd` |
| point-in-time safety | partial. Daily close data is only safe after close unless lagged |

Audit note: coverage does not overlap the 2023-2025 TRACE panel.
It cannot be used immediately for same-period bond-equity factors.

### ETF / Book Views

| Table Or View | Inferred Type | Timestamp | Coverage | Notes |
| --- | --- | --- | --- | --- |
| `book_coverage` | deduplicated order-book coverage | `trade_date` | varies by symbol | Use this for coverage. Do not sum `db_book`, `lob_book`, `lob_msg`, and `lob_ts`. |
| `db_book` | order-book events | `ts_event` | LQD/HYG/JNK deep history | Has bid/ask levels and sizes. |
| `lob_book` | alternate book representation | table schema available | same source-days as `db_book` | Same dataset family. |
| `lob_msg` | alternate message representation | table schema available | same source-days as `db_book` | Same dataset family. |
| `lob_ts` | alternate timestamp representation | table schema available | same source-days as `db_book` | Same dataset family. |
| `etf_l1` | L1 quote/trade view | `trade_date` plus `millis` | limited legacy coverage for SPY/QQQ/IWM | Not same-period with TRACE based on audit query. |
| `rates_l1` | rates L1 view | `time` | not fully profiled | Has `symbol, trade_date, time, type, value, size`. |
| `irf_yield` | rates / futures / yield enriched view | `time`, `timestamp`, `estimated_arrival_time` | not fully profiled | Has bid/ask/mid/spread-style fields. Needs source validation. |

Credit ETF deduplicated coverage:

| Symbol | First Date | Last Date | Days | Rows |
| --- | --- | --- | ---: | ---: |
| HYG | 2019-01-30 | 2026-05-28 | 762 | 128,416,997 |
| JNK | 2019-01-30 | 2026-05-29 | 763 | 107,394,990 |
| LQD | 2019-01-30 | 2026-05-29 | 763 | 216,808,344 |
| TLT | 2019-01-30 | 2021-08-13 | 10 | 7,256,908 |
| VCIT | 2019-01-30 | 2021-08-13 | 10 | 450,901 |
| ZN | 2019-01-30 | 2021-08-13 | 10 | 11,222,571 |

### RFQ Data

No repository-local RFQ table or stream was found.

`event_table.md` describes desired RFQ fields.
It is not an observed dataset.

RFQ inquiry, response, firm-up, dealer-count, protocol, venue, quote-time, and fill-status factors are blocked until a real RFQ source is connected.

### Composite / Evaluated Price Data

No composite bid/ask/mid, spread, OAS, evaluated-price, or vendor fair-value table was found in this repo or confirmed in marketdb.

ETF order-book bid/ask data exists for LQD/HYG/JNK.
That is not a bond-level composite quote.

## Point-In-Time Safety Notes

- TRACE execution time is available.
- TRACE dissemination time is not available at intraday precision.
- TRACE report date is available, but it is not enough for minute-level as-of joins.
- CRSP daily data must be lagged for intraday RFQ prediction.
- Security-master backfill dates are not available.
- Bond-to-equity links have valid date windows, but publication/revision timing is not known.
- ETF order-book data has event timestamps and is safer for intraday factor confirmation.
- Composite and evaluated prices are absent, so revised marks are a future leakage risk, not a current usable input.

## Duplicated Or Competing Implementations

| Area | Implementations | Risk |
| --- | --- | --- |
| acquisition | `bond_alpha.data.acquire` and `bondsim.discovery/preprocess` | Two data entry points use different contracts. |
| side convention | `AGENTS.md` dealer perspective vs `bond_alpha_factors.md` TRACE-style customer buy/sell vs `bondsim` BUY=+1 | High risk. Must be resolved before factors. |
| synthetic truth docs | `bond_alpha/bond_alpha/data/SYNTHETIC_TRUTH.md` and `bond_alpha/data/SYNTHETIC_TRUTH.md` | Two truth docs can drift. |
| project layout | old package `bond_alpha/bond_alpha` and new package `bond_alpha/src/bondsim` | Future work needs one public API boundary. |
| Makefile targets | scaffold echo targets vs `bondsim` CLI commands | Pipeline entry points are competing. |

## Leakage Risks

| Risk | Status | Control Needed |
| --- | --- | --- |
| revised composite prices | blocked input, but high risk if added | require observation timestamp and revision timestamp |
| TRACE reporting delays | active risk | use dissemination timestamp if available; otherwise limit intraday claims |
| end-of-day reference data used intraday | active risk for CRSP and reference data | lag EOD data to next session |
| security-master backfills | active risk | require effective dates and load dates |
| future firm-up or execution status | blocked input, but high risk if RFQ arrives | separate inquiry, response, firm-up, and execution tables |
| inferred trade side from future quotes | active risk if quote signing is added | sign only with quotes observed before print time |
| curve fits using unavailable instruments | active risk | curve universe must be frozen as of prediction time |
| interdealer double reports | active risk | predeclare filtering by research question |
| issuer universe survivorship | active risk | construct train/validation/test universes by as-of membership |
| sparse stale marks | active risk | record staleness and fallback window used |

## Ten Main Blockers Or Ambiguities

1. No confirmed RFQ event table exists.
2. No bond-level composite bid, ask, mid, spread, or evaluated-price history is confirmed.
3. No maturity, rating, sector, duration, convexity, coupon, issue size, or amount outstanding table is confirmed.
4. TRACE side perspective is ambiguous relative to the dealer-perspective project convention.
5. TRACE dissemination timestamp is missing; only execution timestamp and report date are present.
6. `entrd_vol_qt` units are not recorded in the warehouse.
7. `trace` is a 15-issuer panel, not a broad corporate-bond universe.
8. JPM dominates row count and CUSIP count, likely because of structured-note-like issuance.
9. Same-period CRSP daily equity data does not overlap the 2023-2025 TRACE panel.
10. `bond_alpha.data.acquire` and `bondsim.preprocess` define different canonical contracts.

