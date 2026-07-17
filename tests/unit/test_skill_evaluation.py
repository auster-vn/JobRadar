import json
from pathlib import Path

from scripts.evaluate_skill_extractor import MIN_F1, evaluate


def test_labeled_skill_benchmark_meets_quality_gate() -> None:
    examples = json.loads(
        Path("tests/fixtures/nlp_skill_benchmark.json").read_text(encoding="utf-8")
    )

    metrics = evaluate(examples)

    assert metrics["examples"] >= 50
    assert metrics["f1"] >= MIN_F1
    assert metrics["latency_p95_ms"] < 100
