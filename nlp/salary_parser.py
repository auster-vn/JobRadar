import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

USD_TO_VND = Decimal("25000")
MILLION = Decimal("1000000")
NEGOTIABLE_TERMS = (
    "thương lượng",
    "thoa thuan",
    "thỏa thuận",
    "thoả thuận",
    "negotiable",
    "competitive",
    "cạnh tranh",
)


@dataclass(frozen=True, slots=True)
class SalaryRange:
    min_vnd: int | None
    max_vnd: int | None
    negotiable: bool
    source_currency: str = "VND"

    def __post_init__(self) -> None:
        if self.min_vnd is not None and self.max_vnd is not None and self.min_vnd > self.max_vnd:
            raise ValueError("minimum salary cannot exceed maximum salary")


def _number(value: str) -> Decimal:
    cleaned = value.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", cleaned):
        cleaned = re.sub(r"[.,]", "", cleaned)
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid salary number: {value}") from exc


def _vnd(value: str, unit: str | None) -> int:
    amount = _number(value)
    normalized_unit = (unit or "").lower()
    if normalized_unit in {"tr", "triệu", "trieu", "m", "million"} or amount < 1000:
        amount *= MILLION
    return int(amount)


def parse_salary(text: str | None) -> SalaryRange:
    if not text or not text.strip():
        return SalaryRange(None, None, True)
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    annual = bool(re.search(r"/(?:năm|year)|per year|hàng năm", normalized))

    def period(value: int) -> int:
        return round(value / 12) if annual else value

    if any(term in normalized for term in NEGOTIABLE_TERMS):
        return SalaryRange(None, None, True)

    usd_range = re.search(
        r"(?:usd\s*)?\$?\s*([\d.,]+)\s*(?:usd)?\s*[-–—]\s*(?:usd\s*)?\$?\s*([\d.,]+)\s*(?:usd)?",
        normalized,
    )
    has_usd_marker = "$" in normalized or "usd" in normalized
    if usd_range and has_usd_marker:
        low = int(_number(usd_range.group(1)) * USD_TO_VND)
        high = int(_number(usd_range.group(2)) * USD_TO_VND)
        return SalaryRange(period(min(low, high)), period(max(low, high)), False, "USD")

    vnd_range = re.search(
        r"([\d.,]+)\s*(tr|triệu|trieu|m|million)?\s*[-–—]\s*([\d.,]+)\s*(tr|triệu|trieu|m|million|vnd)",
        normalized,
    )
    if vnd_range:
        low = _vnd(vnd_range.group(1), vnd_range.group(2) or vnd_range.group(4))
        high = _vnd(vnd_range.group(3), vnd_range.group(4))
        return SalaryRange(period(min(low, high)), period(max(low, high)), False)

    upper = re.search(
        r"(?:lên đến|tới|up to|upto|tối đa|max)\s*:?\s*\$?\s*"
        r"([\d.,]+)\s*(tr|triệu|trieu|m|million|usd)?",
        normalized,
    )
    if upper:
        currency = "USD" if "$" in upper.group(0) or upper.group(2) == "usd" else "VND"
        value = (
            int(_number(upper.group(1)) * USD_TO_VND)
            if currency == "USD"
            else _vnd(upper.group(1), upper.group(2))
        )
        return SalaryRange(None, period(value), False, currency)

    lower = re.search(
        r"(?:từ|from|minimum|min)\s*:?\s*\$?\s*([\d.,]+)\s*(tr|triệu|trieu|m|million|usd)?",
        normalized,
    )
    if lower:
        currency = "USD" if "$" in lower.group(0) or lower.group(2) == "usd" else "VND"
        value = (
            int(_number(lower.group(1)) * USD_TO_VND)
            if currency == "USD"
            else _vnd(lower.group(1), lower.group(2))
        )
        return SalaryRange(period(value), None, False, currency)

    return SalaryRange(None, None, True)
