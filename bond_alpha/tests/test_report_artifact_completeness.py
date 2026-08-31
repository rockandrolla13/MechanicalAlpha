from bondsim.visualization.report import write_visual_report


def test_visual_report_entrypoint_exists():
    assert callable(write_visual_report)
