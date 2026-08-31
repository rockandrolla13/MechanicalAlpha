import numpy as np
import pandas as pd
import pytest

from mechanical_alpha.models.event_models import ModelTask, TimeSplitConfig, evaluate_task, make_time_ordered_split
from mechanical_alpha.models.metrics import evaluate_binary_predictions


def _model_frame(n: int = 80) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-02 09:30", periods=n, freq="30min")
    imbalance = np.linspace(-1.0, 1.0, n)
    last_side = np.where(np.arange(n) % 3 == 0, 1, -1)
    pressure = imbalance + 0.35 * (last_side == 1)
    target = (pressure > np.median(pressure)).astype(int)
    return pd.DataFrame(
        {
            "prediction_time": timestamps,
            "label_time": timestamps + pd.Timedelta(minutes=30),
            "feature_time": timestamps - pd.Timedelta(minutes=1),
            "target_next_buy": target,
            "last_side": last_side,
            "imbalance": imbalance,
            "run_length": np.arange(n) % 5,
            "spread": np.linspace(0.4, 1.2, n),
            "activity_surprise": np.sin(np.arange(n) / 7.0),
        }
    )


def _task(estimators=("benchmark_unconditional", "benchmark_last_side", "benchmark_imbalance", "logistic_l2")) -> ModelTask:
    return ModelTask(
        task_id="next_trace_side",
        target_column="target_next_buy",
        prediction_timestamp_column="prediction_time",
        label_timestamp_column="label_time",
        feature_timestamp_columns=("feature_time",),
        feature_columns=("imbalance", "last_side", "run_length", "spread", "activity_surprise"),
        last_side_column="last_side",
        imbalance_column="imbalance",
        estimators=estimators,
    )


def test_time_ordered_split_preserves_chronology() -> None:
    frame = _model_frame(30).sample(frac=1.0, random_state=7)
    split = make_time_ordered_split(frame, "prediction_time", TimeSplitConfig(0.6, 0.2, 0.2))

    train_max = frame.loc[split.train_index, "prediction_time"].max()
    validation_min = frame.loc[split.validation_index, "prediction_time"].min()
    validation_max = frame.loc[split.validation_index, "prediction_time"].max()
    test_min = frame.loc[split.test_index, "prediction_time"].min()

    assert train_max < validation_min
    assert validation_max < test_min


def test_point_in_time_guard_rejects_future_feature_time() -> None:
    frame = _model_frame()
    frame.loc[10, "feature_time"] = frame.loc[10, "prediction_time"] + pd.Timedelta(seconds=1)

    with pytest.raises(ValueError, match="future information"):
        evaluate_task(frame, _task())


def test_event_model_scaffold_runs_benchmarks_and_logistic() -> None:
    results = evaluate_task(_model_frame(), _task(), split_config=TimeSplitConfig(0.6, 0.2, 0.2))

    assert set(results) == {
        "benchmark_unconditional",
        "benchmark_last_side",
        "benchmark_imbalance",
        "logistic_l2",
    }
    assert results["logistic_l2"].predictions["probability"].between(0, 1).all()
    assert results["logistic_l2"].metrics.confusion_matrix.keys() == {"tn", "fp", "fn", "tp"}
    assert not results["logistic_l2"].metrics.decile_performance.empty


def test_gradient_boosting_supported_for_toxicity_style_task() -> None:
    task = _task(estimators=("gradient_boosting",))
    results = evaluate_task(_model_frame(120), task, split_config=TimeSplitConfig(0.7, 0.15, 0.15))

    assert "gradient_boosting" in results
    assert results["gradient_boosting"].metrics.log_loss >= 0.0


def test_binary_metrics_handle_single_class_auc_as_nan() -> None:
    metrics = evaluate_binary_predictions(np.ones(8), np.full(8, 0.7))

    assert np.isnan(metrics.roc_auc)
    assert metrics.brier_score >= 0.0
