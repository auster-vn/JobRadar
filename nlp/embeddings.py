from functools import lru_cache
from typing import Protocol, cast

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384


class SentenceEncoder(Protocol):
    def encode(
        self, sentences: list[str], *, normalize_embeddings: bool, show_progress_bar: bool
    ) -> object: ...


@lru_cache(maxsize=1)
def _model() -> SentenceEncoder:
    from sentence_transformers import SentenceTransformer

    return cast(SentenceEncoder, SentenceTransformer(MODEL_NAME))


def encode_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = _model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    if not hasattr(vectors, "tolist"):
        raise TypeError("embedding model returned an unsupported value")
    rows = cast(list[list[float]], vectors.tolist())
    if any(len(row) != EMBEDDING_DIMENSIONS for row in rows):
        raise ValueError(f"expected {EMBEDDING_DIMENSIONS}-dimension embeddings")
    return rows
