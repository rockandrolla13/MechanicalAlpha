import pandas as pd

from bondsim.visualization.liquidity import ranked_event_rates


def test_plot_data_reproducibility():
    frame = pd.DataFrame({"bond": ["b", "a", "a", "b"]})
    left = ranked_event_rates(frame, "bond", 2)
    right = ranked_event_rates(frame, "bond", 2)
    pd.testing.assert_frame_equal(left, right)
