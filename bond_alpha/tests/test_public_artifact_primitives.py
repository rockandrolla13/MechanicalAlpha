from pathlib import Path

import pandas as pd

from mechanical_alpha.hashing import file_sha256, stable_json_hash
from mechanical_alpha.io import manifest_for_files, write_json, write_parquet


def test_public_json_and_parquet_writers_are_deterministic(tmp_path: Path):
    payload = {"b": 2, "a": 1}
    json_path = write_json(payload, tmp_path / "nested" / "payload.json")
    assert json_path.exists()
    assert json_path.read_text().startswith("{\n  \"a\"")

    frame = pd.DataFrame({"event_id": ["e1", "e2"], "value": [1.0, 2.0]})
    parquet_path = write_parquet(frame, tmp_path / "tables" / "events.parquet")
    loaded = pd.read_parquet(parquet_path)
    pd.testing.assert_frame_equal(loaded, frame)

    manifest = manifest_for_files([json_path, parquet_path, tmp_path / "missing"], {"config": payload})
    assert manifest["config_hash"] == stable_json_hash(payload)
    assert [item["path"] for item in manifest["files"]] == [str(json_path), str(parquet_path)]
    assert manifest["files"][0]["sha256"] == file_sha256(json_path)
