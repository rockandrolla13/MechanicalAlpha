"""Local data discovery and column mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bondsim.config import BondSimConfig
from bondsim.io import write_json


CANONICAL_MAPPING = {
    "timestamp": "trd_exctn_ts",
    "bond_id": "cusip",
    "issuer_id": "company_symbol",
    "side": "rpt_side_cd",
    "price": "rptd_pr",
    "notional": "entrd_vol_qt",
    "is_interdealer": "cntra_mp_id",
    "trade_type": "cntra_mp_id",
    "venue": None,
    "bid": None,
    "ask": None,
    "mid": None,
    "fair_value": None,
    "yield": "yld_pt",
    "oas": None,
    "duration": None,
    "convexity": None,
    "maturity": None,
    "rating": None,
    "sector": None,
}


@dataclass(frozen=True)
class DiscoveryResult:
    source_name: str
    mapping: dict[str, str | None]
    profile: dict[str, Any]


def run_discovery(config: BondSimConfig) -> DiscoveryResult:
    profile = _discover_marketdb()
    mapping = dict(CANONICAL_MAPPING)
    report_root = config.paths.report_root
    report_root.mkdir(parents=True, exist_ok=True)
    Path("configs").mkdir(parents=True, exist_ok=True)
    Path("configs/column_mapping.generated.yaml").write_text(
        yaml.safe_dump({"source": "marketdb.trace", "columns": mapping}, sort_keys=False)
    )
    write_json(profile, report_root / "data_profile.json")
    (report_root / "data_discovery.md").write_text(_render_report(profile, mapping))
    return DiscoveryResult("marketdb.trace", mapping, profile)


def _discover_marketdb() -> dict[str, Any]:
    try:
        import marketdb

        con = marketdb.connect()
        profile = con.sql(
            """
            SELECT count(*) AS rows,
                   count(DISTINCT cusip) AS bond_count,
                   count(DISTINCT company_symbol) AS issuer_count,
                   min(trd_exctn_dt) AS first_date,
                   max(trd_exctn_dt) AS last_date,
                   sum(company_symbol IS NULL)::BIGINT AS missing_issuer_rows,
                   sum(cntra_mp_id='D' AND rpt_side_cd='B')::BIGINT AS interdealer_double_report_rows
            FROM trace
            """
        ).df().iloc[0].to_dict()
        profile["schema"] = con.sql("DESCRIBE trace").df().to_dict(orient="records")
        profile["side_contra_counts"] = con.sql(
            """
            SELECT rpt_side_cd, cntra_mp_id, count(*) AS rows
            FROM trace GROUP BY 1,2 ORDER BY rows DESC
            """
        ).df().to_dict(orient="records")
        profile["issuer_counts"] = con.sql(
            """
            SELECT company_symbol, count(*) AS rows, count(DISTINCT cusip) AS bonds
            FROM trace WHERE company_symbol IS NOT NULL
            GROUP BY 1 ORDER BY rows DESC
            """
        ).df().to_dict(orient="records")
        con.close()
        profile["source_available"] = True
        profile["source_type"] = "executed_public_or_enhanced_trace_prints"
        return json.loads(json.dumps(profile, default=str))
    except Exception as exc:
        return {
            "source_available": False,
            "source_type": "none",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _render_report(profile: dict[str, Any], mapping: dict[str, str | None]) -> str:
    missing = [key for key, value in mapping.items() if value is None]
    return f"""# Data Discovery

## Selected Sources

| Source | Why Selected | Inferred Type |
| --- | --- | --- |
| `marketdb.trace` | Local warehouse has TRACE executions/prints and required timing, price, side, size fields. | {profile.get('source_type')} |

No repository-local CSV, Parquet, Arrow, Feather, or DuckDB files were selected.

## Coverage

- Rows: `{profile.get('rows')}`
- Bonds: `{profile.get('bond_count')}`
- Issuers: `{profile.get('issuer_count')}`
- Date coverage: `{profile.get('first_date')}` to `{profile.get('last_date')}`
- Missing issuer rows: `{profile.get('missing_issuer_rows')}`
- Likely interdealer duplicate rows: `{profile.get('interdealer_double_report_rows')}`

## Canonical Mapping

```yaml
{yaml.safe_dump(mapping, sort_keys=False).strip()}
```

## Side Semantics

`rpt_side_cd` is mapped as `B -> BUY = +1` and `S -> SELL = -1`.
Confidence is medium.
Evidence: TRACE side codes are present as `B` and `S`, but the warehouse does not include a richer field proving whether this is customer, dealer, or reporting-party perspective.

## Units

- Price: TRACE reported price. Values are treated as par-price units where `100` means par and `0.01` means one cent.
- Notional: `entrd_vol_qt`. The warehouse skill states units are not recorded. The simulator treats this as par quantity.
- Timestamp: `trd_exctn_ts`. Treated as UTC-like naive timestamps for local simulation reproducibility.

## Missing Fields

{', '.join(f'`{field}`' for field in missing)}

## Degradations

- Rating, maturity, duration, sector, OAS, bid, ask, mid, and fair value are unavailable in `marketdb.trace`.
- Fair value route falls back to a robust transaction-price proxy.
- Sector/rating/maturity buckets use `unknown` unless external reference data is added later.
- SynthCity is optional. If plugin introspection or candidate fitting fails, empirical conditional bootstrap is selected.
- Interdealer is derived as `cntra_mp_id == "D"`.
"""


def profile_frame(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "null_rates": frame.isna().mean().round(6).to_dict(),
    }
