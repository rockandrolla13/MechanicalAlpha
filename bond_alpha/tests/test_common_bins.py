import numpy as np
import pandas as pd

from bondsim.visualization.marks import notional_tail_table


def test_common_quantiles_are_reused():
    qs = np.array([0.5, 0.9])
    frame = pd.DataFrame({"notional": [100.0, 200.0, 300.0]})
    assert notional_tail_table(frame, qs)["quantile"].tolist() == [0.5, 0.9]
