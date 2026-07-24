import sys
from types import ModuleType
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


def test_model_loader_pins_trusted_safetensors_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def load(model_name: str, **kwargs: Any) -> FakeModel:
        captured.update(model_name=model_name, **kwargs)
        return FakeModel(embeddings.EMBEDDING_DIMENSIONS)

    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = load  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    embeddings._model.cache_clear()

    try:
        embeddings._model()
    finally:
        embeddings._model.cache_clear()

    assert captured == {
        "model_name": embeddings.MODEL_NAME,
        "revision": embeddings.MODEL_REVISION,
        "trust_remote_code": False,
        "model_kwargs": {"use_safetensors": True},
    }


def test_encode_texts_returns_normalized_model_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "_model", lambda: FakeModel(embeddings.EMBEDDING_DIMENSIONS))

    assert len(embeddings.encode_texts(["Python engineer"])[0]) == 384


def test_encode_texts_rejects_wrong_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "_model", lambda: FakeModel(3))

    with pytest.raises(ValueError, match="384-dimension"):
        embeddings.encode_texts(["Python engineer"])
