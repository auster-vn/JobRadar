import re

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "một": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "sáu": 6,
    "bảy": 7,
    "tám": 8,
    "chín": 9,
    "mười": 10,
}
UNIT_PATTERN = r"years?|yrs?|năm|months?|mos?|tháng"
CONTEXT_PATTERN = re.compile(
    r"experience|experienced|kinh\s+nghiệm|thâm\s+niên|"
    r"at\s+least|min(?:imum)?|more\s+than|over|from|"
    r"tối\s+thiểu|ít\s+nhất|trên|từ",
    re.IGNORECASE,
)
NO_EXPERIENCE_PATTERN = re.compile(
    r"no(?:\s+prior)?(?:\s+work)?\s+experience\s+required|"
    r"không\s+yêu\s+cầu(?:\s+kinh\s+nghiệm)?",
    re.IGNORECASE,
)


def _replace_number_words(value: str) -> str:
    pattern = re.compile(
        rf"\b({'|'.join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True))})\b",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: str(NUMBER_WORDS[match.group(0).casefold()]), value)


def _years(value: int, unit: str) -> int:
    return value // 12 if unit.casefold() in {"month", "months", "mos", "mo", "tháng"} else value


def _has_context(text: str, start: int, end: int, *, allow_bare: bool) -> bool:
    if allow_bare:
        return True
    window = text[max(0, start - 48) : min(len(text), end + 48)]
    return bool(CONTEXT_PATTERN.search(window) or "+" in text[start:end])


def parse_experience_years(
    value: str | None, *, allow_bare: bool = False
) -> tuple[int | None, int | None]:
    """Extract required experience without treating arbitrary years as tenure."""
    if not value or not value.strip():
        return None, None
    normalized = _replace_number_words(value.casefold().replace("–", "-").replace("—", "-"))
    if NO_EXPERIENCE_PATTERN.search(normalized):
        return 0, 0

    candidates: list[tuple[int, int | None]] = []
    occupied: list[tuple[int, int]] = []
    range_pattern = re.compile(
        rf"\b(\d{{1,2}})\s*({UNIT_PATTERN})?\s*(?:-|to|đến|tới)\s*"
        rf"(\d{{1,2}})\s*\+?\s*({UNIT_PATTERN})\b",
        re.IGNORECASE,
    )
    for match in range_pattern.finditer(normalized):
        if not _has_context(normalized, match.start(), match.end(), allow_bare=allow_bare):
            continue
        low = _years(int(match.group(1)), match.group(2) or match.group(4))
        high = _years(int(match.group(3)), match.group(4))
        if 0 <= low <= high <= 30:
            candidates.append((low, high))
            occupied.append(match.span())

    single_pattern = re.compile(rf"\b(\d{{1,2}})\s*\+?\s*({UNIT_PATTERN})\b", re.IGNORECASE)
    for match in single_pattern.finditer(normalized):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        if not _has_context(normalized, match.start(), match.end(), allow_bare=allow_bare):
            continue
        years = _years(int(match.group(1)), match.group(2))
        if 0 <= years <= 30:
            candidates.append((years, None))

    if not candidates:
        return None, None
    minimum = max(candidate[0] for candidate in candidates)
    matching_maxima = [high for low, high in candidates if low == minimum and high is not None]
    if matching_maxima:
        return minimum, max(matching_maxima)
    return minimum, minimum if allow_bare else None
