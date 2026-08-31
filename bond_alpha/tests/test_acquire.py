from pathlib import Path

import pandas as pd

from bond_alpha.data.acquire import FINRA_PUBLIC_LIMITATIONS, TAPE_COLUMNS, load_tape


def test_synthetic_loader_returns_canonical_tape() -> None:
    tape = load_tape(
        {
            "type": "synthetic",
            "n_bonds": 20,
            "start": "2021-01-01",
            "end": "2021-01-29",
            "seed": 11,
        }
    )

    assert list(tape.columns) == TAPE_COLUMNS
    assert not tape.empty
    assert tape["ts"].is_monotonic_increasing
    assert set(tape["side_flag"].dropna().unique()).issubset({-1, 1})
    assert (tape["par_volume"] > 0).all()


def test_finra_public_loader_parses_capped_volume(tmp_path: Path) -> None:
    source = tmp_path / "finra_public.csv"
    pd.DataFrame(
        {
            "CUSIP": ["ABC123456", "XYZ987654"],
            "Execution Date/Time": ["2023-01-03 10:00:00", "2023-01-03 10:01:00"],
            "Price": [99.5, 101.25],
            "Quantity": ["5MM+", "1MM+"],
            "Side": ["client sells", "client buys"],
        }
    ).to_csv(source, index=False)

    tape = load_tape({"type": "finra_public", "path": source})

    assert list(tape.columns) == TAPE_COLUMNS
    assert tape["par_volume"].tolist() == [5_000_000.0, 1_000_000.0]
    assert tape["side_flag"].tolist() == [1, -1]
    assert tape["contra_party_type"].tolist() == ["unknown", "unknown"]


def test_finra_public_limitations_are_documented() -> None:
    assert "5MM+" in FINRA_PUBLIC_LIMITATIONS
    assert "1MM+" in FINRA_PUBLIC_LIMITATIONS
    assert "not the uncapped regulatory tape" in FINRA_PUBLIC_LIMITATIONS
