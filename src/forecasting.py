from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import TargetEncoder


CATEGORICAL_FEATURES = [
    "food_item",
    "category",
    "meal",
    "facility",
    "service_area",
    "menu_variant",
    "menu_component",
]
NUMERIC_FEATURES = [
    "resident_count",
    "day_of_week",
    "month",
    "menu_week",
    "is_weekend",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


@dataclass
class ModelResult:
    model: Pipeline
    metrics: dict
    train_rows: int
    test_rows: int
    cutoff_date: str
    target: str


def _add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["service_date"] = pd.to_datetime(work["service_date"])
    work["day_of_week"] = work.service_date.dt.dayofweek.astype(int)
    work["month"] = work.service_date.dt.month.astype(int)
    work["is_weekend"] = (work.day_of_week >= 5).astype(int)
    # Four-week menu position; using elapsed week number is enough for a repeating menu.
    origin = work.service_date.min().normalize()
    work["menu_week"] = (((work.service_date.dt.normalize() - origin).dt.days // 7) % 4 + 1).astype(int)
    for col in CATEGORICAL_FEATURES:
        if col not in work.columns:
            work[col] = "Unknown"
        work[col] = work[col].fillna("Unknown").astype(str)
    for col in NUMERIC_FEATURES:
        if col not in work.columns:
            work[col] = 0
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
    return work


def _time_split(work: pd.DataFrame, test_fraction: float = 0.20):
    dates = np.array(sorted(work.service_date.dt.normalize().unique()))
    if len(dates) < 8:
        raise ValueError("At least 8 distinct service dates are required for time-based model evaluation.")
    split_idx = max(1, min(len(dates) - 1, int(math.floor(len(dates) * (1.0 - test_fraction)))))
    cutoff = pd.Timestamp(dates[split_idx])
    train = work[work.service_date.dt.normalize() < cutoff].copy()
    test = work[work.service_date.dt.normalize() >= cutoff].copy()
    if train.empty or test.empty:
        raise ValueError("Unable to create a time-based train/test split.")
    return train, test, cutoff


def _pipeline() -> Pipeline:
    preprocess = ColumnTransformer(
        transformers=[
            (
                "cat",
                TargetEncoder(target_type="continuous", smooth="auto", random_state=42),
                CATEGORICAL_FEATURES,
            ),
            ("num", "passthrough", NUMERIC_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    model = HistGradientBoostingRegressor(
        learning_rate=0.07,
        max_iter=220,
        max_leaf_nodes=31,
        min_samples_leaf=20,
        l2_regularization=0.25,
        random_state=42,
    )
    return Pipeline([("prep", preprocess), ("model", model)])


def _wape(y_true, y_pred) -> float | None:
    denom = float(np.abs(y_true).sum())
    if denom <= 1e-9:
        return None
    return float(np.abs(y_true - y_pred).sum() / denom * 100.0)


def _metrics(y_true, y_pred, baseline_pred) -> dict:
    mae = float(mean_absolute_error(y_true, y_pred))
    baseline_mae = float(mean_absolute_error(y_true, baseline_pred))
    rmse = float(mean_squared_error(y_true, y_pred) ** 0.5)
    r2 = float(r2_score(y_true, y_pred)) if len(y_true) > 1 else None
    improvement = ((baseline_mae - mae) / baseline_mae * 100.0) if baseline_mae > 1e-9 else None
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "wape": _wape(np.asarray(y_true), np.asarray(y_pred)),
        "baseline_mae": baseline_mae,
        "mae_improvement_pct": improvement,
    }


def _prep_baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Simple operational baseline: median kg/resident by category + meal.

    It intentionally does not memorize individual food items; the ML model must add
    value from food, menu variant, service area and calendar context.
    """
    tr = train.copy()
    tr = tr[tr.resident_count > 0]
    tr["kg_per_resident"] = tr.prepared_kg / tr.resident_count
    category = tr.groupby(["category", "meal"], dropna=False).kg_per_resident.median()
    meal = tr.groupby("meal", dropna=False).kg_per_resident.median()
    global_ratio = float(tr.kg_per_resident.median()) if not tr.empty else 0.15
    preds = []
    for row in test.itertuples():
        ratio = category.get((row.category, row.meal), np.nan)
        if pd.isna(ratio):
            ratio = meal.get(row.meal, np.nan)
        if pd.isna(ratio):
            ratio = global_ratio
        preds.append(max(0.0, float(ratio) * float(row.resident_count)))
    return np.asarray(preds)


def _plate_baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Simple meal-quality baseline: mean plate-waste % by category + variant."""
    category = train.groupby(["category", "menu_variant"], dropna=False).waste_percentage.mean()
    meal = train.groupby("meal", dropna=False).waste_percentage.mean()
    global_pct = float(train.waste_percentage.mean())
    preds = []
    for row in test.itertuples():
        value = category.get((row.category, row.menu_variant), np.nan)
        if pd.isna(value):
            value = meal.get(row.meal, np.nan)
        if pd.isna(value):
            value = global_pct
        preds.append(float(value))
    return np.asarray(preds)


def train_preparation_model(df: pd.DataFrame) -> ModelResult:
    work = df[df.waste_type.eq("Production Waste")].copy()
    work = work.dropna(subset=["prepared_kg", "resident_count", "service_date"])
    work = work[(pd.to_numeric(work.prepared_kg, errors="coerce") > 0) & (pd.to_numeric(work.resident_count, errors="coerce") > 0)]
    if len(work) < 500:
        raise ValueError("At least 500 production-waste observations are recommended for the ML preparation model.")
    work = _add_calendar_features(work)
    train, test, cutoff = _time_split(work)
    pipe = _pipeline()
    pipe.fit(train[FEATURES], train.prepared_kg.astype(float))
    pred = np.maximum(0.0, pipe.predict(test[FEATURES]))
    baseline = _prep_baseline(train, test)
    metrics = _metrics(test.prepared_kg.to_numpy(dtype=float), pred, baseline)
    return ModelResult(pipe, metrics, len(train), len(test), cutoff.date().isoformat(), "prepared_kg")


def train_plate_waste_model(df: pd.DataFrame) -> ModelResult:
    work = df[df.waste_type.eq("Plate Waste")].copy()
    work = work.dropna(subset=["waste_percentage", "resident_count", "service_date"])
    work = work[(pd.to_numeric(work.resident_count, errors="coerce") > 0)]
    work["waste_percentage"] = pd.to_numeric(work.waste_percentage, errors="coerce")
    work = work.dropna(subset=["waste_percentage"])
    if len(work) < 500:
        raise ValueError("At least 500 plate-waste observations are recommended for the ML meal-quality model.")
    work = _add_calendar_features(work)
    train, test, cutoff = _time_split(work)
    pipe = _pipeline()
    pipe.fit(train[FEATURES], train.waste_percentage.astype(float))
    pred = np.clip(pipe.predict(test[FEATURES]), 0.0, 100.0)
    baseline = _plate_baseline(train, test)
    metrics = _metrics(test.waste_percentage.to_numpy(dtype=float), pred, baseline)
    return ModelResult(pipe, metrics, len(train), len(test), cutoff.date().isoformat(), "waste_percentage")


def context_frame(
    *,
    service_date,
    food_item: str,
    category: str,
    meal: str,
    facility: str,
    service_area: str,
    menu_variant: str,
    menu_component: str,
    resident_count: int,
    origin_date=None,
) -> pd.DataFrame:
    d = pd.Timestamp(service_date)
    origin = pd.Timestamp(origin_date) if origin_date is not None else d
    menu_week = int(((d.normalize() - origin.normalize()).days // 7) % 4 + 1)
    return pd.DataFrame([{
        "food_item": food_item,
        "category": category or "Unknown",
        "meal": meal,
        "facility": facility,
        "service_area": service_area,
        "menu_variant": menu_variant,
        "menu_component": menu_component,
        "resident_count": int(resident_count),
        "day_of_week": int(d.dayofweek),
        "month": int(d.month),
        "menu_week": menu_week,
        "is_weekend": int(d.dayofweek >= 5),
    }])


def predict_preparation(result: ModelResult, context: pd.DataFrame) -> float:
    return max(0.0, float(result.model.predict(context[FEATURES])[0]))


def predict_plate_waste(result: ModelResult, context: pd.DataFrame) -> float:
    return float(np.clip(result.model.predict(context[FEATURES])[0], 0.0, 100.0))
