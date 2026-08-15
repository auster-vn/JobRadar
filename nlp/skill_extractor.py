import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TAXONOMY_PATH = Path(__file__).with_name("skills_taxonomy.json")
NICE_TO_HAVE = ("nice to have", "preferred", "advantage", "plus", "bonus", "ưu tiên", "lợi thế")


@dataclass(frozen=True, slots=True)
class ExtractedSkills:
    required: list[str]
    nice_to_have: list[str]


@lru_cache
def _matcher() -> tuple[re.Pattern[str], dict[str, str]]:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for item in taxonomy:
        for alias in {item["name"], *item.get("aliases", [])}:
            aliases[alias.casefold()] = item["name"]
    expression = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    return re.compile(rf"(?<![\w])(?:{expression})(?![\w])", re.I), aliases


def extract_skills(text: str) -> ExtractedSkills:
    required: set[str] = set()
    optional: set[str] = set()
    seen: set[str] = set()
    pattern, aliases = _matcher()
    for match in pattern.finditer(text):
        canonical = aliases[match.group().casefold()]
        if canonical in seen:
            continue
        seen.add(canonical)
        context = text[max(0, match.start() - 100) : match.start()].lower()
        target = optional if any(marker in context for marker in NICE_TO_HAVE) else required
        target.add(canonical)
    required -= optional
    return ExtractedSkills(sorted(required), sorted(optional))
