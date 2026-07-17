import pytest

from nlp.salary_parser import SalaryRange, parse_salary


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("15 - 25 triệu", SalaryRange(15_000_000, 25_000_000, False)),
        ("15tr-25tr", SalaryRange(15_000_000, 25_000_000, False)),
        ("$2,000 - $3,000", SalaryRange(50_000_000, 75_000_000, False, "USD")),
        ("Lên đến 30tr", SalaryRange(None, 30_000_000, False)),
        ("Từ 18 triệu", SalaryRange(18_000_000, None, False)),
        ("Tới $ 3,000 /tháng", SalaryRange(None, 75_000_000, False, "USD")),
        ("200tr-700tr ₫/năm", SalaryRange(16_666_667, 58_333_333, False)),
        ("Thương lượng", SalaryRange(None, None, True)),
        (None, SalaryRange(None, None, True)),
    ],
)
def test_parse_salary(raw: str | None, expected: SalaryRange) -> None:
    assert parse_salary(raw) == expected


def test_parser_normalizes_reversed_range() -> None:
    assert parse_salary("30 - 20 triệu") == SalaryRange(20_000_000, 30_000_000, False)
