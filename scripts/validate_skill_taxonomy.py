import json
from pathlib import Path

TAXONOMY = Path("nlp/skills_taxonomy.json")
METADATA = Path("nlp/skills_taxonomy.meta.json")


def validate() -> None:
    entries = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or len(entries) < 500:
        raise ValueError("taxonomy must contain at least 500 entries")
    claimed: dict[str, str] = {}
    categories: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ValueError(f"entry {index} must be an object")
        name = item.get("name")
        category = item.get("category")
        aliases = item.get("aliases")
        if not isinstance(name, str) or len(name.strip()) < 2:
            raise ValueError(f"entry {index} has invalid name")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"entry {index} has invalid category")
        if not isinstance(aliases, list) or not all(isinstance(value, str) for value in aliases):
            raise ValueError(f"entry {index} has invalid aliases")
        categories.add(category)
        for value in [name, *aliases]:
            key = value.casefold()
            if key in claimed and claimed[key] != name:
                raise ValueError(f"ambiguous term {value!r}: {claimed[key]!r} and {name!r}")
            claimed[key] = name
    if metadata.get("entry_count") != len(entries):
        raise ValueError("metadata entry_count does not match taxonomy")
    if len(categories) < 5:
        raise ValueError("taxonomy must cover at least five categories")


if __name__ == "__main__":
    validate()
    print("Skill taxonomy is valid.")
