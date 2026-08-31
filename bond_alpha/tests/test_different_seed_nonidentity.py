from bondsim.calibration.ensemble import build_seed_manifest


def test_different_seed_manifests_differ():
    assert build_seed_manifest(1, 2) != build_seed_manifest(2, 2)
