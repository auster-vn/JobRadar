import pytest

from scripts.rotate_cv_encryption_key import _read_rotation_keys


def test_rotation_keys_must_be_strong_and_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLD_CV_ENCRYPTION_KEY", "o" * 32)
    monkeypatch.setenv("NEW_CV_ENCRYPTION_KEY", "n" * 32)

    assert _read_rotation_keys() == ("o" * 32, "n" * 32)


@pytest.mark.parametrize(
    ("old_key", "new_key"),
    [("short", "n" * 32), ("o" * 32, "short"), ("same" * 8, "same" * 8)],
)
def test_rotation_rejects_weak_or_reused_keys(
    monkeypatch: pytest.MonkeyPatch, old_key: str, new_key: str
) -> None:
    monkeypatch.setenv("OLD_CV_ENCRYPTION_KEY", old_key)
    monkeypatch.setenv("NEW_CV_ENCRYPTION_KEY", new_key)

    with pytest.raises(ValueError):
        _read_rotation_keys()
