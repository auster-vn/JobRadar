import re
import unicodedata
from collections.abc import Iterable

LOCATION_NORMALIZER_REVISION = "2026-07-19.1"

_NEW_MARKER = re.compile(r"\s*\(\s*mới\s*\)\s*", re.IGNORECASE)
_OTHER_LOCATIONS = re.compile(r"^(?:\d+\s+)?nơi\s+khác$", re.IGNORECASE)


def _lookup_key(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
        .encode("ascii", "ignore")
        .decode()
        .casefold()
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


_CANONICAL_CITIES = {
    "da nang": "Da Nang",
    "danang": "Da Nang",
    "ha noi": "Ha Noi",
    "hanoi": "Ha Noi",
    "hn": "Ha Noi",
    "ho chi minh": "Ho Chi Minh",
    "hcm": "Ho Chi Minh",
    "hcmc": "Ho Chi Minh",
    "sai gon": "Ho Chi Minh",
    "thanh pho ho chi minh": "Ho Chi Minh",
    "tp hcm": "Ho Chi Minh",
    "tp ho chi minh": "Ho Chi Minh",
}


def normalize_location(value: str | None) -> str | None:
    """Return a stable market label for one location value."""
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", _NEW_MARKER.sub(" ", value)).strip(" ,;|-/")
    if not cleaned or _OTHER_LOCATIONS.fullmatch(cleaned):
        return None
    return _CANONICAL_CITIES.get(_lookup_key(cleaned), cleaned)


def normalize_locations(values: Iterable[str]) -> list[str]:
    """Normalize and deduplicate an ordered collection of source locations."""
    normalized: list[str] = []
    for value in values:
        for part in re.split(r"\s+&\s+", value):
            location = normalize_location(part)
            if location is not None and location not in normalized:
                normalized.append(location)
    return normalized


def normalize_primary_location(value: str | None) -> str | None:
    locations = normalize_locations([value]) if value else []
    return locations[0] if locations else None
