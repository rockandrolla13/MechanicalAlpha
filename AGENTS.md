# AGENTS.md

## Project Context
Always explain in plain english.
short clear sentences and not long paragraphs.
Before any implementation you invoke /blueprint and use /ideate, /design and /code review.
MechanicalAlpha is a research and implementation workspace for anonymous corporate bond RFQ alpha features. The core objective is to transform RFQ events, bond fair values, spread data, issuer metadata, and optional market/news data into leakage-safe predictive features for:

- future bond fair-value return
- future spread-implied return
- future factor-residual return

The project is not primarily a quote optimizer. Keep feature research, target definition, data contracts, and backtest methodology separate from execution or quoting logic unless explicitly requested.

## Current Reference Files

- `anonymous_rfq_alpha_feature_research_spec_from_quantcraft.md`: main research specification and data/feature framework.
- `event_table.md`: compact RFQ event input table.

Read these before changing project direction, naming conventions, or data assumptions.

## Core Domain Rules

- Treat every feature as an as-of feature. Do not use data that would not have been available at the RFQ timestamp or prediction timestamp.
- Preserve the sign convention from the spec: dealer perspective uses `side_t = +1` for client sells to dealer and `side_t = -1` for client buys from dealer.
- Prefer return-oriented feature signs where a positive feature means positive expected future bond return.
- Keep horizons explicit. The canonical horizons are `30m`, `2h`, `1d`, `3d`, `5d`, and `10d`.
- Separate price fair-value returns, spread-implied returns, and factor-residual returns.
- When adding formulas, define symbols locally and specify units.
- When adding feature ideas, state required inputs, as-of timestamp, expected sign, forecast horizon, and leakage risks.

## Engineering Guidelines

- Keep documentation, feature specs, code, tests, and notebooks organized by purpose.
- Prefer small, reproducible scripts or modules over ad hoc notebook-only logic for production-relevant calculations.
- Do not commit credentials, proprietary data, raw RFQ exports, tokens, API keys, or client-identifying information.
- Use anonymized or synthetic examples in docs and tests.
- Avoid silently changing financial sign conventions, target definitions, or time alignment behavior.
- If implementation files are added later, include focused tests for time alignment, side/sign convention, horizon construction, and missing-data handling.

## Suggested Structure

If the project grows beyond markdown specs, use a structure like:

```text
docs/
  specs/
  research_notes/
src/
  mechanical_alpha/
    data/
    features/
    targets/
    backtests/
tests/
notebooks/
```

Do not create this structure preemptively unless there is actual content to place in it.

## Validation Expectations

Before considering feature code complete, verify:

- no future data enters feature construction
- timestamp joins are as-of joins, not nearest future joins
- target windows are computed after the prediction timestamp
- RFQ side mapping is tested
- spread-return signs are tested
- cross-sectional grouping does not leak future constituents or metadata
- missing, stale, and sparse bond data cases are handled deliberately

## Git Guidance

- This directory is its own Git repository.
- Remote: `https://github.com/rockandrolla13/MechanicalAlpha.git`
- Keep commits scoped to this project directory.
- Do not modify parent repository files from this project unless explicitly asked.
