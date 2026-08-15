import uuid

from api.services.storage import _object_path


def test_cv_storage_path_is_tenant_scoped_and_unique() -> None:
    user_id = uuid.uuid4()

    first = _object_path(user_id, "resume.pdf")
    second = _object_path(user_id, "resume.pdf")

    assert first.startswith(f"{user_id}/cv/")
    assert first.endswith(".pdf")
    assert first != second


def test_cv_storage_path_rejects_unsafe_suffix() -> None:
    user_id = uuid.uuid4()

    assert _object_path(user_id, "resume.superlongextension").endswith(".bin")
