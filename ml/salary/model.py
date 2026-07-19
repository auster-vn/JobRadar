import json
from pathlib import Path
from typing import Any


class SalaryPredictor:
    """Mean, Q25 and Q75 XGBoost models trained on log salary."""

    base_params = {
        "n_estimators": 400,
        "learning_rate": 0.03,
        "max_depth": 2,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_lambda": 10,
        "random_state": 42,
        "n_jobs": 8,
    }

    def __init__(self) -> None:
        import xgboost as xgb

        self.model_mean = xgb.XGBRegressor(objective="reg:squarederror", **self.base_params)
        self.model_q25 = xgb.XGBRegressor(
            objective="reg:quantileerror", quantile_alpha=0.25, **self.base_params
        )
        self.model_q75 = xgb.XGBRegressor(
            objective="reg:quantileerror", quantile_alpha=0.75, **self.base_params
        )
        self.q25_offset = 0.0
        self.q75_offset = 0.0
        self.interval_radius = 0.0

    def fit(self, features: Any, target: Any) -> None:
        self.fit_mean(features, target)
        self.fit_quantiles(features, target)

    def fit_mean(self, features: Any, target: Any) -> None:
        import numpy as np

        target_log = np.log1p(target)
        self.model_mean.fit(features, target_log)

    def fit_quantiles(self, features: Any, target: Any) -> None:
        """Fit only interval models for out-of-fold calibration."""
        import numpy as np

        target_log = np.log1p(target)
        self.model_q25.fit(features, target_log)
        self.model_q75.fit(features, target_log)

    def calibrate(
        self,
        q25_offset: float,
        q75_offset: float,
        interval_radius: float = 0.0,
    ) -> None:
        if interval_radius < 0:
            raise ValueError("interval_radius must be non-negative")
        self.q25_offset = float(q25_offset)
        self.q75_offset = float(q75_offset)
        self.interval_radius = float(interval_radius)

    def predict_many(self, features: Any) -> dict[str, Any]:
        import numpy as np

        mean = np.expm1(self.model_mean.predict(features))
        return {"salary_estimate": mean, **self.predict_quantiles(features, mean=mean)}

    def predict_quantiles(self, features: Any, *, mean: Any = None) -> dict[str, Any]:
        import numpy as np

        raw_q25 = np.maximum(0.0, np.expm1(self.model_q25.predict(features)) + self.q25_offset)
        raw_q75 = np.maximum(0.0, np.expm1(self.model_q75.predict(features)) + self.q75_offset)
        lower = np.minimum(raw_q25, raw_q75)
        upper = np.maximum(raw_q25, raw_q75)
        if self.interval_radius:
            if mean is None:
                mean = np.expm1(self.model_mean.predict(features))
            lower = np.minimum(lower, np.maximum(0.0, mean - self.interval_radius))
            upper = np.maximum(upper, mean + self.interval_radius)
        return {
            "salary_p25": lower,
            "salary_p75": upper,
        }

    def predict(self, features: Any) -> dict[str, int | str]:
        predictions = self.predict_many(features)
        return {
            "salary_estimate": int(predictions["salary_estimate"][0]),
            "salary_p25": int(predictions["salary_p25"][0]),
            "salary_p75": int(predictions["salary_p75"][0]),
            "currency": "VND",
        }

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.model_mean.get_booster().save_model(directory / "mean.json")
        self.model_q25.get_booster().save_model(directory / "q25.json")
        self.model_q75.get_booster().save_model(directory / "q75.json")
        (directory / "calibration.json").write_text(
            json.dumps(
                {
                    "q25_offset": self.q25_offset,
                    "q75_offset": self.q75_offset,
                    "interval_radius": self.interval_radius,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> "SalaryPredictor":
        predictor = cls()
        predictor.model_mean.load_model(directory / "mean.json")
        predictor.model_q25.load_model(directory / "q25.json")
        predictor.model_q75.load_model(directory / "q75.json")
        calibration_path = directory / "calibration.json"
        if calibration_path.exists():
            calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            predictor.calibrate(
                calibration.get("q25_offset", 0.0),
                calibration.get("q75_offset", 0.0),
                calibration.get("interval_radius", 0.0),
            )
        return predictor
