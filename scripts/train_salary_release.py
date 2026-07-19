import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from api.core.config import get_settings
from ml.salary.evaluate import evaluation_failures
from ml.salary.training import load_frozen_holdout, load_salary_rows, train_and_evaluate
from ml.serving import PublishedSalaryModel


async def train_release(output_dir: Path) -> dict[str, Any]:
    settings = get_settings()
    if re.fullmatch(r"[0-9a-f]{40}", settings.source_revision) is None:
        raise ValueError("SOURCE_REVISION must be a 40-character Git SHA")
    if not settings.salary_holdout_manifest:
        raise ValueError("SALARY_HOLDOUT_MANIFEST is required for release training")

    result = train_and_evaluate(
        await load_salary_rows(),
        output_dir=output_dir,
        frozen_holdout=load_frozen_holdout(Path(settings.salary_holdout_manifest)),
    )
    if result.get("status") != "published":
        raise RuntimeError(f"salary release training did not publish: {result.get('reason')}")

    artifact_dir = output_dir / "current"
    metadata = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    failures = evaluation_failures(
        metadata,
        require_data_ready=True,
        require_committed_revision=True,
    )
    if failures:
        raise RuntimeError(f"salary release evidence failed: {', '.join(failures)}")
    if not PublishedSalaryModel(
        artifact_dir,
        expected_source_revision=settings.source_revision,
    ).available:
        raise RuntimeError("published salary release artifact cannot be loaded")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the release-bound salary model")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/salary"))
    args = parser.parse_args()
    result = asyncio.run(train_release(args.output_dir))
    print(
        json.dumps(
            {
                "status": result["status"],
                "run_id": result["run_id"],
                "test_mape": result["test_mape"],
                "test_size": result["test_size"],
                "test_segment_count": result["test_segment_count"],
                "data_ready": result["data_ready"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
