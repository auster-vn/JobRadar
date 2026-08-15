import json
from pathlib import Path

import pytest

from ml.serving import REQUIRED_ARTIFACTS
from scripts.install_salary_model import install

REVISION = "a" * 40


def _bundle(path: Path, revision: str = REVISION) -> None:
    path.mkdir(parents=True)
    for name in REQUIRED_ARTIFACTS - {"metadata.json"}:
        (path / name).write_text(name, encoding="utf-8")
    (path / "metadata.json").write_text(
        json.dumps(
            {
                "status": "published",
                "source_revision": revision,
                "failed_gates": [],
                "metrics": {"test_mape": 0.12},
                "data_readiness": {"ready": True},
            }
        ),
        encoding="utf-8",
    )


def test_installs_a_release_bound_salary_model_idempotently(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    target = tmp_path / "artifacts" / REVISION
    _bundle(seed)

    assert install(seed, target, expected_revision=REVISION, required=True)
    assert install(seed, target, expected_revision=REVISION, required=True)
    assert {path.name for path in target.iterdir()} == REQUIRED_ARTIFACTS


def test_rejects_a_salary_model_from_another_revision(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    _bundle(seed, revision="b" * 40)

    with pytest.raises(ValueError, match="source revision"):
        install(
            seed,
            tmp_path / "target",
            expected_revision=REVISION,
            required=True,
        )


def test_development_image_can_omit_a_model_seed(tmp_path: Path) -> None:
    assert not install(
        tmp_path / "missing",
        tmp_path / "target",
        expected_revision="local",
        required=False,
    )
