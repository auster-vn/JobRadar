import argparse
import json
import time
from pathlib import Path
from typing import TypedDict

from nlp.skill_extractor import extract_skills

MIN_EXAMPLES = 50
MIN_F1 = 0.80


class BenchmarkExample(TypedDict):
    id: str
    text: str
    expected: list[str]


def evaluate(examples: list[BenchmarkExample]) -> dict[str, float | int]:
    if len(examples) < MIN_EXAMPLES:
        raise ValueError(f"benchmark requires at least {MIN_EXAMPLES} examples")
    true_positive = false_positive = false_negative = 0
    latencies: list[float] = []
    for example in examples:
        started = time.perf_counter()
        result = extract_skills(example["text"])
        latencies.append((time.perf_counter() - started) * 1000)
        predicted = {*result.required, *result.nice_to_have}
        expected = set(example["expected"])
        true_positive += len(predicted & expected)
        false_positive += len(predicted - expected)
        false_negative += len(expected - predicted)
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    ordered_latency = sorted(latencies)
    p95_index = min(len(ordered_latency) - 1, int(len(ordered_latency) * 0.95))
    return {
        "examples": len(examples),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "latency_p95_ms": round(ordered_latency[p95_index], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the labeled skill extraction corpus")
    parser.add_argument(
        "--dataset", type=Path, default=Path("tests/fixtures/nlp_skill_benchmark.json")
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    examples: list[BenchmarkExample] = json.loads(args.dataset.read_text(encoding="utf-8"))
    metrics = evaluate(examples)
    rendered = json.dumps(metrics, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if float(metrics["f1"]) < MIN_F1:
        raise SystemExit(f"skill extraction F1 {metrics['f1']} is below {MIN_F1}")


if __name__ == "__main__":
    main()
