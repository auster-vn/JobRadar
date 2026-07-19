from pathlib import Path
from typing import Any

from nlp.location_normalizer import normalize_location
from nlp.title_normalizer import canonical_role


class SalaryFeatureEncoder:
    """Fit text and categorical salary features using training rows only."""

    def __init__(self, title_feature_limit: int = 256, skill_feature_limit: int = 256) -> None:
        self.title_feature_limit = title_feature_limit
        self.skill_feature_limit = skill_feature_limit
        self.title_vectorizer: Any = None
        self.skill_vectorizer: Any = None
        self.category_encoder: Any = None

    @staticmethod
    def _titles(rows: list[dict[str, Any]]) -> list[str]:
        documents = []
        for row in rows:
            raw = str(row.get("title") or "").strip()
            normalized = str(row.get("title_normalized") or "").strip()
            documents.append(
                " | ".join(dict.fromkeys(value for value in (raw, normalized) if value))
            )
        return documents

    @staticmethod
    def _skill_documents(rows: list[dict[str, Any]]) -> list[str]:
        return [
            " | ".join(str(skill) for skill in row.get("skills_required") or []) for row in rows
        ]

    @staticmethod
    def _categories(rows: list[dict[str, Any]]) -> list[list[str]]:
        return [
            [
                str(row.get("job_level") or "mid"),
                normalize_location(str(row.get("location") or "")) or "unknown",
                canonical_role(row.get("title_normalized")) or "other",
            ]
            for row in rows
        ]

    @staticmethod
    def _numeric(rows: list[dict[str, Any]]) -> Any:
        import numpy as np
        from scipy.sparse import csr_matrix

        values = np.asarray(
            [[max(0.0, float(row.get("experience_years") or 0))] for row in rows],
            dtype=np.float32,
        )
        return csr_matrix(values)

    def fit(self, rows: list[dict[str, Any]]) -> "SalaryFeatureEncoder":
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import OneHotEncoder

        self.title_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            min_df=2,
            max_features=self.title_feature_limit,
            sublinear_tf=True,
        ).fit(self._titles(rows))
        self.skill_vectorizer = TfidfVectorizer(
            token_pattern=r"(?u)[^|]+",  # noqa: S106 - scikit tokenization expression.
            lowercase=True,
            min_df=2,
            max_features=self.skill_feature_limit,
        ).fit(self._skill_documents(rows))
        self.category_encoder = OneHotEncoder(handle_unknown="ignore").fit(self._categories(rows))
        return self

    def transform(self, rows: list[dict[str, Any]]) -> Any:
        from scipy.sparse import hstack

        if not self.title_vectorizer or not self.skill_vectorizer or not self.category_encoder:
            raise RuntimeError("salary feature encoder has not been fitted")
        return hstack(
            [
                self.title_vectorizer.transform(self._titles(rows)),
                self.skill_vectorizer.transform(self._skill_documents(rows)),
                self.category_encoder.transform(self._categories(rows)),
                self._numeric(rows),
            ],
            format="csr",
        )

    def fit_transform(self, rows: list[dict[str, Any]]) -> Any:
        return self.fit(rows).transform(rows)

    def save(self, path: Path) -> None:
        import joblib

        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path) -> "SalaryFeatureEncoder":
        import joblib

        encoder = joblib.load(path)
        if not isinstance(encoder, cls):
            raise TypeError("artifact is not a SalaryFeatureEncoder")
        return encoder
