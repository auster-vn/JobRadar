import pytest

from nlp.experience_parser import parse_experience_years


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("At least four years of experience with APIs", (4, None)),
        ("3-5 years of relevant professional experience", (3, 5)),
        ("3–8+ years of experience depending on role level", (3, 8)),
        ("Tối thiểu 2 năm kinh nghiệm phát triển phần mềm", (2, None)),
        ("Kinh nghiệm từ 3 đến 4 năm", (3, 4)),
        ("Tối thiểu từ 3 năm đến 8 năm kinh nghiệm BA", (3, 8)),
        ("5+ years working in pre-sales", (5, None)),
        ("No prior work experience required", (0, 0)),
        ("Không yêu cầu kinh nghiệm", (0, 0)),
        ("Company founded in 2015 with salary up to 5000 USD", (None, None)),
        ("Use Java 8 and ISO 27001 standards", (None, None)),
    ],
)
def test_parse_contextual_experience(text: str, expected: tuple[int | None, int | None]) -> None:
    assert parse_experience_years(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("18 tháng", (1, 1)), ("2 - 4 năm", (2, 4)), ("Trao đổi khi phỏng vấn", (None, None))],
)
def test_parse_structured_experience_field(
    text: str, expected: tuple[int | None, int | None]
) -> None:
    assert parse_experience_years(text, allow_bare=True) == expected
