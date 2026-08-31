"""RFQ evaluation placeholders backed by public synthetic prints."""

from __future__ import annotations

import pandas as pd


def event_side_balance(frame: pd.DataFrame) -> dict[str, float]:
    return {"customer_buy_share": float(frame["side"].eq(1).mean()), "rows": int(len(frame))}
