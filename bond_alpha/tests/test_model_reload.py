import json

from bondsim.calibration.ensemble import _selected_model_reload_success


def test_selected_model_reload_record(tmp_path):
    (tmp_path / "selected_models.json").write_text(json.dumps({"selected": "empirical_fallback"}))
    assert _selected_model_reload_success(tmp_path)
