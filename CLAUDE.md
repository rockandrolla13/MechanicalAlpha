# CLAUDE.md
Always explain in plain english.
short clear sentences and not long paragraphs.
Before any implementation you invoke /blueprint and use /ideate, /design and /code review.
All the code will needs to be smoke test and regression tested
## Project Brief

MechanicalAlpha is a research/codebase for anonymous corporate bond RFQ alpha feature development. The main task is to design leakage-safe features that predict future bond fair-value returns, spread-implied returns, and factor-residual returns from RFQ events and market data.

Start by reading:

- `anonymous_rfq_alpha_feature_research_spec_from_quantcraft.md`
- `event_table.md`
- `AGENTS.md`

## Scope of This Repository

**This repo is the implementation side of the project.** Work here means code: estimators, LP
lvers, CI tests, experiments, and tests. No theory.
## Working Principles

- Preserve as-of correctness. Features must only use information available at the RFQ timestamp or prediction timestamp.
- Be explicit about timestamps. Distinguish request time, quote time, market-data observation time, and target window endpoints.
- Keep the project focused on alpha research and feature construction, not quote optimization, unless the user asks for quoting logic.
- Avoid using real client names, raw RFQ records, credentials, or proprietary identifiers in committed examples.
- Prefer synthetic examples and anonymized identifiers.

## Domain Conventions

Dealer-perspective side convention:

```text
side_t = +1  means client sells bond to dealer
side_t = -1  means client buys bond from dealer
```

Return-oriented alpha convention:

```text
positive feature value -> positive expected future bond return
```

Canonical forecast horizons:

```text
30m, 2h, 1d, 3d, 5d, 10d
```

Canonical targets:

- price fair-value return
- spread-implied return
- factor-residual return

## Documentation Standards

When adding or changing a feature specification, include:

- feature name
- intuition
- required inputs
- exact timestamp used for feature availability
- formula or algorithm
- expected sign
- forecast horizons
- leakage risks
- sparse-data behavior
- validation checks

When adding formulas, define every symbol and state whether values are price, spread, duration-scaled return, notional, count, or normalized score.

## Code Standards

If implementation code is introduced:

- Use clear modules for `data`, `features`, `targets`, and `backtests`.
- Keep feature generation deterministic and testable.
- Prefer typed Python and explicit schemas where practical.
- Use as-of joins for market and reference data.
- Do not bury sign flips or horizon logic in unnamed constants.
- Add tests for side mapping, spread-return sign, target construction, timestamp joins, and missing-data behavior.

## Testing Priorities

Minimum checks for feature code:

- no feature row depends on observations after its prediction timestamp
- target returns start after the prediction timestamp
- client-sell pressure has the expected sign transformation
- spread tightening maps to positive spread-implied return
- issuer, sector, rating, and maturity group features do not use future group membership
- stale marks and missing fair values are handled explicitly

## Git Notes

This project has its own Git repository in the `MechanicalAlpha` directory.

Remote:

```text
https://github.com/rockandrolla13/MechanicalAlpha.git
```

Do not modify or stage files from the parent `GitRepos` repository unless the user explicitly asks.
