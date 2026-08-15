import argparse
import json
from pathlib import Path
from typing import Any

TARGET = Path("nlp/skills_taxonomy.json")
METADATA = Path("nlp/skills_taxonomy.meta.json")


def _normalized_aliases(values: list[object]) -> list[str]:
    return sorted(
        {value.strip() for value in values if isinstance(value, str) and len(value.strip()) >= 2},
        key=str.casefold,
    )


def merge(upstream: list[dict[str, Any]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    claimed: set[str] = set()

    def add(item: dict[str, Any], *, preserve: bool) -> None:
        name = str(item.get("name", "")).strip()
        if len(name) < 2 or name.casefold() in claimed:
            return
        source_aliases = item.get("aliases", item.get("synonyms", []))
        aliases = [
            alias
            for alias in _normalized_aliases(list(source_aliases or []))
            if alias.casefold() not in claimed and alias.casefold() != name.casefold()
        ]
        types = item.get("type") or []
        category = item.get("category") or (types[0] if types else "Technology")
        record: dict[str, Any] = {
            "name": name,
            "category": str(category),
            "aliases": aliases,
        }
        languages = item.get("supportedProgrammingLanguages") or []
        if languages:
            record["language"] = str(languages[0])
        related = item.get("related") or item.get("impliesKnowingSkills") or []
        if related:
            record["related"] = sorted({str(value) for value in related})
        if preserve:
            record.update(
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"name", "category", "aliases"}
                }
            )
            record["aliases"] = aliases
        merged.append(record)
        claimed.add(name.casefold())
        claimed.update(alias.casefold() for alias in aliases)

    for item in existing:
        add(item, preserve=True)
    for item in sorted(upstream, key=lambda value: str(value.get("name", "")).casefold()):
        add(item, preserve=False)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a MIND ontology snapshot into JobRadar")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    upstream = json.loads(args.snapshot.read_text(encoding="utf-8"))
    existing = json.loads(TARGET.read_text(encoding="utf-8"))
    merged = merge(upstream, existing)
    TARGET.write_text(json.dumps(merged, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    METADATA.write_text(
        json.dumps(
            {
                "version": "2026.07",
                "entry_count": len(merged),
                "upstream": "MIND Tech Skills & Concepts Ontology",
                "upstream_revision": args.revision,
                "license": "MIT",
                "source": "https://github.com/MIND-TechAI/MIND-tech-ontology",
                "modified": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
