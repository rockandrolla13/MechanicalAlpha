import pandas as pd

from bondsim.visualization.data_quality import missingness_table


def test_report_table_generation():
    table = missingness_table(pd.DataFrame({"a": [1, None], "b": [2, 3]}))
    assert set(table.columns) == {"field", "missing_rate"}
    assert table.loc[table["field"].eq("a"), "missing_rate"].item() == 0.5
