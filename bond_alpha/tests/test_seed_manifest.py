from bondsim.calibration.ensemble import build_seed_manifest


def test_seed_manifest_separates_child_streams():
    manifest = build_seed_manifest(20260830, 3)
    assert len(manifest["seeds"]) == 3
    assert {"fit_seed", "simulation_seed", "mark_pool_seed", "bootstrap_seed", "plot_sampling_seed"}.issubset(manifest["seeds"][0])
    assert build_seed_manifest(20260830, 3) == manifest
