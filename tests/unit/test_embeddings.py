from typing import Any

import pytest

from nlp import embeddings


class FakeVectors:
    def __init__(self, values: list[list[float]]) -> None:
        self.values = values

    def tolist(self) -> list[list[float]]:
        return self.values


class FakeModel:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def encode(self, sentences: list[str], **_: Any) -> FakeVectors:
        return FakeVectors([[0.0] * self.dimensions for _ in sentences])


def test_encode_texts_returns_normalized_model_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "_model", lambda: FakeModel(embeddings.EMBEDDING_DIMENSIONS))

    assert len(embeddings.encode_texts(["Python engineer"])[0]) == 384


def test_encode_texts_rejects_wrong_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "_model", lambda: FakeModel(3))

    with pytest.raises(ValueError, match="384-dimension"):
        embeddings.encode_texts(["Python engineer"])
