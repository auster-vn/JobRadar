from typing import Any

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("xgboost")

from api.schemas.salary import SalaryPredictionRequest
from ml.features.salary_features import SalaryFeatureEncoder
from ml.salary.model import SalaryPredictor
from ml.serving import PublishedSalaryModel

SUPPORTED_SEGMENTS = [{"role": "Backend Developer", "level": "senior", "location": "Ha Noi"}]


def _training_rows() -> list[dict[str, Any]]:
    return [
        {
            "title": "Python Backend Developer" if index % 2 else "Java Backend Developer",
            "job_level": "junior" if index < 15 else "senior",
            "location": "Ha Noi" if index % 3 else "Ho Chi Minh",
            "experience_years": index % 7,
            "skills_required": ["Python", "PostgreSQL"] if index % 2 else ["Java", "SQL"],
        }
        for index in range(30)
    ]


def test_salary_title_features_include_raw_and_canonical_titles() -> None:
    documents = SalaryFeatureEncoder._titles(
        [{"title": "Kỹ sư máy chủ", "title_normalized": "Backend Developer"}]
    )

    assert documents == ["Kỹ sư máy chủ | Backend Developer"]


def test_salary_categories_include_structured_canonical_role() -> None:
    categories = SalaryFeatureEncoder._categories(
        [
            {
                "title_normalized": "Senior Backend Developer",
                "job_level": "senior",
                "location": "Ha Noi",
            },
            {"title_normalized": "Graphic Designer", "job_level": "mid", "location": None},
        ]
    )

    assert categories == [
        ["senior", "Ha Noi", "Backend Developer"],
        ["mid", "unknown", "other"],
    ]


def test_salary_artifacts_round_trip_without_test_vocabulary_leakage(tmp_path: Any) -> None:
    rows = _training_rows()
    unseen = [
        {
            "title": "COBOL Mainframe Engineer",
            "job_level": "mid",
            "location": "Da Nang",
            "experience_years": 4,
            "skills_required": ["COBOL"],
        }
    ]
    encoder = SalaryFeatureEncoder().fit(rows)
    assert not any(
        "cobol" in feature for feature in encoder.title_vectorizer.get_feature_names_out()
    )
    features = encoder.transform(rows)
    target = np.asarray([12_000_000 + index * 750_000 for index in range(len(rows))])
    predictor = SalaryPredictor()
    predictor.fit(features, target)
    predictor.calibrate(-250_000, 500_000, 1_000_000)
    expected = predictor.predict_many(encoder.transform(unseen))

    predictor.save(tmp_path)
    encoder.save(tmp_path / "encoder.joblib")
    restored_encoder = SalaryFeatureEncoder.load(tmp_path / "encoder.joblib")
    actual = SalaryPredictor.load(tmp_path).predict_many(restored_encoder.transform(unseen))

    for key in expected:
        np.testing.assert_allclose(expected[key], actual[key], rtol=1e-5, atol=1.0)


def test_serving_loads_only_a_published_model_below_the_gate(tmp_path: Any) -> None:
    import json

    rows = _training_rows()
    encoder = SalaryFeatureEncoder().fit(rows)
    predictor = SalaryPredictor()
    predictor.fit(
        encoder.transform(rows),
        np.asarray([12_000_000 + index * 750_000 for index in range(len(rows))]),
    )
    predictor.save(tmp_path)
    encoder.save(tmp_path / "encoder.joblib")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "status": "rejected",
                "metrics": {"test_mape": 0.10},
                "data_readiness": {
                    "ready": True,
                    "supported_segments": SUPPORTED_SEGMENTS,
                },
            }
        ),
        encoding="utf-8",
    )
    serving_model = PublishedSalaryModel(tmp_path)
    assert not serving_model.available

    metadata.write_text(
        json.dumps(
            {
                "status": "published",
                "metrics": {"test_mape": float("nan")},
                "data_readiness": {
                    "ready": True,
                    "supported_segments": SUPPORTED_SEGMENTS,
                },
            }
        ),
        encoding="utf-8",
    )
    assert not serving_model.available

    metadata.write_text(
        json.dumps({"status": "published", "metrics": {"test_mape": 0.10}}),
        encoding="utf-8",
    )
    assert not serving_model.available

    metadata.write_text(
        json.dumps(
            {
                "status": "published",
                "source_revision": "a" * 40,
                "metrics": {"test_mape": 0.10},
                "data_readiness": {
                    "ready": True,
                    "supported_segments": SUPPORTED_SEGMENTS,
                },
            }
        ),
        encoding="utf-8",
    )
    request = SalaryPredictionRequest(
        title="Python Backend Developer",
        level="senior",
        location="Ha Noi",
        experience_years=5,
        skills=["Python", "PostgreSQL"],
    )
    result = serving_model.predict(request)

    assert result["currency"] == "VND"
    assert result["salary_p25"] <= result["salary_p75"]
    assert PublishedSalaryModel(
        tmp_path,
        expected_source_revision="a" * 40,
    ).available
    assert not PublishedSalaryModel(
        tmp_path,
        expected_source_revision="b" * 40,
    ).available

    unsupported = request.model_copy(update={"location": "Da Nang"})
    with pytest.raises(RuntimeError, match="does not support"):
        serving_model.predict(unsupported)


def test_quantile_only_fit_does_not_require_mean_model() -> None:
    rows = _training_rows()
    encoder = SalaryFeatureEncoder().fit(rows)
    predictor = SalaryPredictor()
    predictor.fit_quantiles(
        encoder.transform(rows),
        np.asarray([12_000_000 + index * 750_000 for index in range(len(rows))]),
    )

    prediction = predictor.predict_quantiles(encoder.transform(rows[:2]))

    assert len(prediction["salary_p25"]) == 2
    assert np.all(prediction["salary_p25"] <= prediction["salary_p75"])
