"""Generic point-in-time event model scaffolding.

The model layer consumes precomputed feature and label frames.
It does not import feature implementations or source adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from mechanical_alpha.models.metrics import BinaryClassificationMetrics, evaluate_binary_predictions

EstimatorName = Literal[
    "benchmark_unconditional",
    "benchmark_last_side",
    "benchmark_imbalance",
    "logistic_l2",
    "gradient_boosting",
]


@dataclass(frozen=True)
class TimeSplitConfig:
    """Time-ordered split fractions."""

    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    test_fraction: float = 0.15

    def validate(self) -> None:
        total = self.train_fraction + self.validation_fraction + self.test_fraction
        if not np.isclose(total, 1.0):
            raise ValueError("split fractions must sum to 1.0")
        if min(self.train_fraction, self.validation_fraction, self.test_fraction) <= 0:
            raise ValueError("split fractions must be positive")


@dataclass(frozen=True)
class TimeSplit:
    """Index partitions for a chronological train/validation/test split."""

    train_index: pd.Index
    validation_index: pd.Index
    test_index: pd.Index


@dataclass(frozen=True)
class ModelTask:
    """A binary event-prediction task over an already-built modeling frame."""

    task_id: str
    target_column: str
    prediction_timestamp_column: str
    feature_columns: tuple[str, ...]
    label_timestamp_column: str | None = None
    feature_timestamp_columns: tuple[str, ...] = ()
    last_side_column: str | None = None
    imbalance_column: str | None = None
    estimators: tuple[EstimatorName, ...] = (
        "benchmark_unconditional",
        "benchmark_last_side",
        "benchmark_imbalance",
        "logistic_l2",
    )
    positive_label: int = 1
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRunResult:
    """Predictions and metrics for one estimator on one task."""

    task_id: str
    estimator: EstimatorName
    metrics: BinaryClassificationMetrics
    predictions: pd.DataFrame


def make_time_ordered_split(
    frame: pd.DataFrame,
    timestamp_column: str,
    config: TimeSplitConfig | None = None,
) -> TimeSplit:
    """Create deterministic chronological train/validation/test indices."""

    split_config = config or TimeSplitConfig()
    split_config.validate()
    _require_columns(frame, [timestamp_column])

    ordered = frame.sort_values(timestamp_column, kind="mergesort")
    n_rows = len(ordered)
    if n_rows < 3:
        raise ValueError("at least three rows are required for train/validation/test splitting")

    train_end = max(1, int(np.floor(n_rows * split_config.train_fraction)))
    validation_end = max(train_end + 1, int(np.floor(n_rows * (split_config.train_fraction + split_config.validation_fraction))))
    validation_end = min(validation_end, n_rows - 1)

    return TimeSplit(
        train_index=ordered.index[:train_end],
        validation_index=ordered.index[train_end:validation_end],
        test_index=ordered.index[validation_end:],
    )


def evaluate_task(
    frame: pd.DataFrame,
    task: ModelTask,
    *,
    split_config: TimeSplitConfig | None = None,
    random_state: int = 20260830,
) -> dict[str, ModelRunResult]:
    """Fit configured benchmarks and models, then evaluate on the test period."""

    validate_modeling_frame(frame, task)
    split = make_time_ordered_split(frame, task.prediction_timestamp_column, split_config)
    train = frame.loc[split.train_index]
    test = frame.loc[split.test_index]
    y_train = train[task.target_column].astype(int)
    y_test = test[task.target_column].astype(int)

    results: dict[str, ModelRunResult] = {}
    for estimator in task.estimators:
        probabilities = _predict_probabilities(estimator, train, y_train, test, task, random_state)
        predictions = pd.DataFrame(
            {
                "prediction_timestamp": test[task.prediction_timestamp_column].values,
                "target": y_test.values,
                "probability": probabilities,
            },
            index=test.index,
        )
        results[estimator] = ModelRunResult(
            task_id=task.task_id,
            estimator=estimator,
            metrics=evaluate_binary_predictions(y_test, probabilities),
            predictions=predictions,
        )
    return results


def validate_modeling_frame(frame: pd.DataFrame, task: ModelTask) -> None:
    """Check schema and point-in-time constraints before fitting."""

    required = [task.target_column, task.prediction_timestamp_column, *task.feature_columns]
    if task.label_timestamp_column is not None:
        required.append(task.label_timestamp_column)
    if task.last_side_column is not None:
        required.append(task.last_side_column)
    if task.imbalance_column is not None:
        required.append(task.imbalance_column)
    required.extend(task.feature_timestamp_columns)
    _require_columns(frame, required)

    target_values = set(frame[task.target_column].dropna().astype(int).unique().tolist())
    if not target_values.issubset({0, 1}):
        raise ValueError(f"{task.target_column} must be binary with values 0/1")

    prediction_time = pd.to_datetime(frame[task.prediction_timestamp_column])
    if task.label_timestamp_column is not None:
        label_time = pd.to_datetime(frame[task.label_timestamp_column])
        if (label_time <= prediction_time).any():
            raise ValueError("label timestamps must be after prediction timestamps")

    for column in task.feature_timestamp_columns:
        feature_time = pd.to_datetime(frame[column])
        if (feature_time > prediction_time).any():
            raise ValueError(f"feature timestamp column {column} contains future information")


def _predict_probabilities(
    estimator: EstimatorName,
    train: pd.DataFrame,
    y_train: pd.Series,
    test: pd.DataFrame,
    task: ModelTask,
    random_state: int,
) -> np.ndarray:
    if estimator == "benchmark_unconditional":
        return np.full(len(test), _bounded_mean(y_train), dtype=float)
    if estimator == "benchmark_last_side":
        return _conditional_probability(train, y_train, test, task.last_side_column)
    if estimator == "benchmark_imbalance":
        if task.imbalance_column is None:
            return np.full(len(test), _bounded_mean(y_train), dtype=float)
        if y_train.nunique() < 2:
            return np.full(len(test), _bounded_mean(y_train), dtype=float)
        return _fit_logistic(train[[task.imbalance_column]], y_train, random_state).predict_proba(
            test[[task.imbalance_column]]
        )[:, 1]
    if estimator == "logistic_l2":
        if y_train.nunique() < 2:
            return np.full(len(test), _bounded_mean(y_train), dtype=float)
        return _fit_logistic(train[list(task.feature_columns)], y_train, random_state).predict_proba(
            test[list(task.feature_columns)]
        )[:, 1]
    if estimator == "gradient_boosting":
        if y_train.nunique() < 2:
            return np.full(len(test), _bounded_mean(y_train), dtype=float)
        model = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("model", GradientBoostingClassifier(random_state=random_state, max_depth=2)),
            ]
        )
        model.fit(train[list(task.feature_columns)], y_train)
        return model.predict_proba(test[list(task.feature_columns)])[:, 1]
    raise ValueError(f"unknown estimator: {estimator}")


def _fit_logistic(features: pd.DataFrame, target: pd.Series, random_state: int) -> Pipeline:
    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    solver="lbfgs",
                    max_iter=1000,
                    random_state=random_state,
                ),
            ),
        ]
    )
    model.fit(features, target)
    return model


def _conditional_probability(
    train: pd.DataFrame,
    y_train: pd.Series,
    test: pd.DataFrame,
    column: str | None,
) -> np.ndarray:
    if column is None:
        return np.full(len(test), _bounded_mean(y_train), dtype=float)

    global_rate = _bounded_mean(y_train)
    rates = train.assign(_target=y_train.values).groupby(column, observed=True)["_target"].mean().to_dict()
    return np.asarray([np.clip(rates.get(value, global_rate), 1e-6, 1.0 - 1e-6) for value in test[column]])


def _bounded_mean(values: pd.Series) -> float:
    return float(np.clip(values.mean(), 1e-6, 1.0 - 1e-6))


def _require_columns(frame: pd.DataFrame, columns: list[str] | tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
