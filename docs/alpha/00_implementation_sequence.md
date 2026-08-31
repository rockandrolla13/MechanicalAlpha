# Implementation Sequence

Date: 2026-08-30

This is the proposed next-stage path.
It is not implemented in this audit.

## Guardrails

- Do not implement factors until the data contract is accepted.
- Do not use RFQ-only fields unless a real RFQ source is connected.
- Do not assume client identity exists.
- Do not use daily close data for intraday predictions unless lagged.
- Do not use TRACE execution time as publication time without documenting the limitation.
- Do not mix dealer-perspective and TRACE-style side signs.

## Proposed Sequence

1. Resolve sign convention.
   - Decide whether `rpt_side_cd=B` means customer buy, dealer buy, or reporting-party buy.
   - Add a side mapping test.
   - Files to change next: `config/alpha/data_contract_draft.yaml`, future data normalization code.

2. Lock the TRACE canonical event table.
   - Define event id.
   - Define interdealer filtering.
   - Define report-delay policy.
   - Define size units.
   - Files to change next: future `src/mechanical_alpha/data/trace.py` or `bond_alpha/src/bondsim/preprocess.py`.

3. Add reference-data ingestion only if a real source exists.
   - Required fields: maturity, rating, sector, coupon, amount outstanding, duration.
   - Do not backfill without effective dates.
   - Files to change next: new config under `config/alpha/`, docs under `docs/alpha/`.

4. Build trade-price proxy targets.
   - Start with F15-style rolling median and VWAP.
   - Record staleness and fallback window.
   - Keep this separate from vendor fair value.
   - Files to change next: future `src/mechanical_alpha/targets/price_proxy.py`.

5. Implement immediate TRACE-only factors.
   - First candidates: B4, B9, B11, B14, A1, A4.
   - Add tests for as-of windows and sparse bonds.
   - Files to change next: future `src/mechanical_alpha/features/trace_flow.py`, `tests/`.

6. Add ambiguous signed-flow factors after sign validation.
   - Candidates: B1, B3, B5, B10, B13, B15, A16.
   - Each factor must state whether positive means positive expected future bond return.

7. Add ETF/rates confirmation features.
   - Use LQD/HYG/JNK first because they overlap the TRACE window.
   - Use as-of joins on event timestamps.
   - Avoid full order-book scans without symbol and date filters.

8. Add curve and residual families only after reference data exists.
   - Candidates: A6, A7, A8, A9, A10, A15.
   - Need maturity, duration, rating, sector, and fair-value/spread route.

9. Add RFQ-specific factors only after RFQ data exists.
   - Separate inquiry, response, firm-up, and execution events.
   - Do not let RFQ requests create price-impact labels unless explicitly modeled.

10. Add replay/backtest.
    - Use time-blocked splits and embargo.
    - Store feature availability timestamps.
    - Store target start and target end timestamps.

## Exact Files Proposed For Next Stage

- `config/alpha/data_contract_draft.yaml`
- `docs/alpha/00_factor_capability_matrix.md`
- `docs/alpha/00_repository_and_data_audit.md`
- `docs/alpha/00_implementation_sequence.md`
- future `src/mechanical_alpha/data/trace.py`
- future `src/mechanical_alpha/schema.py`
- future `src/mechanical_alpha/targets/price_proxy.py`
- future `src/mechanical_alpha/features/trace_flow.py`
- future `tests/test_trace_contract.py`
- future `tests/test_asof_windows.py`
- future `tests/test_side_convention.py`

## First Buildable Batch

The first production batch should be small.

It should include:

- canonical TRACE print normalization
- temporal split
- rolling trade-price proxy target
- B4 Hawkes/intensity state
- B9 moving-average deviation reversal
- B11 range-position reversal
- B14 price-volume rank divergence
- A1 clock seasonality on TRACE prints
- A4 low-volatility reversal on trade-price proxy

## Deferred Batches

Curve families wait for security master and fair value.

RFQ families wait for actual RFQ data.

News and theme families wait for timestamped news/sentiment data.

Client-toxicity families remain blocked because the market is anonymous.

