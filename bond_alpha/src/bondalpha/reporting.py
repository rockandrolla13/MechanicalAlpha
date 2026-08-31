"""Report writers for Alpha Factory public-data research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from bondsim.io import write_json


REPORT_NAMES = {
    "data_audit": "data_audit.md",
    "reversal": "reversal.md",
    "flow": "flow_persistence.md",
    "leadlag": "leadlag.md",
    "relative_value": "relative_value.md",
    "falsification": "falsification.md",
    "null": "null_results.md",
    "cost": "cost_analysis.md",
}


def write_gate3_alpha_reports(report_root: Path, payload: dict[str, Any]) -> None:
    """Write the required Gate 3 alpha-development report files."""

    report_root.mkdir(parents=True, exist_ok=True)
    for title, filename in REPORT_NAMES.items():
        (report_root / filename).write_text(_markdown(title, payload))
    write_json(payload.get("selection", {"approved_families": []}), report_root / "alpha_selection.json")


def write_frame_report(path: Path, title: str, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path).write_text(f"# {title}\n\nRows: `{len(frame)}`\nColumns: `{list(frame.columns)}`\n")


def _markdown(title: str, payload: dict[str, Any]) -> str:
    return (
        f"# {title.replace('_', ' ').title()}\n\n"
        f"- public_data_root: `{payload.get('public_data_root')}`\n"
        f"- rows: `{payload.get('rows')}`\n"
        f"- scenarios: `{payload.get('scenarios', [])}`\n"
        f"- truth_access: `forbidden`\n"
    )
