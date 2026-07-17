import json
from datetime import UTC, datetime

import pytest

from nlp.salary_parser import SalaryRange, parse_salary
from scrapers.vietnamworks.parser import parse_listing, parse_search_response


def test_parse_structured_next_data() -> None:
    payload = {
        "props": {
            "pageProps": {
                "outstandingJobs": [
                    {
                        "jobTitle": "Senior Data Engineer",
                        "company": "Data Co",
                        "location": "Hồ Chí Minh, Hà Nội",
                        "prettySalary": "$ 1,500-2,500 /tháng",
                        "url": "https://www.vietnamworks.com/senior-data-engineer-2078617-jv?utm=x",
                        "onlineOnText": "Đăng 6 ngày trước",
                        "logoUrl": "https://images.vietnamworks.com/logo/data.png",
                    }
                ]
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
    jobs = parse_listing(html, now=datetime(2026, 7, 14, tzinfo=UTC))
    assert len(jobs) == 1
    assert jobs[0].platform_job_id == "2078617"
    assert jobs[0].location == ["Hồ Chí Minh", "Hà Nội"]
    assert str(jobs[0].source_url) == "https://www.vietnamworks.com/senior-data-engineer-2078617-jv"
    assert jobs[0].posted_at == datetime(2026, 7, 8, tzinfo=UTC)


def test_parse_search_api_response() -> None:
    jobs, pages = parse_search_response(
        {
            "meta": {"code": 200, "nbPages": 9},
            "data": [
                {
                    "jobId": 2073758,
                    "jobTitle": "Senior Software Engineer",
                    "companyName": "One Mount",
                    "companyLogo": "https://images.vietnamworks.com/logo.png",
                    "isSalaryVisible": True,
                    "salaryCurrency": "USD",
                    "salaryMin": 0,
                    "salaryMax": 2500,
                    "jobLevel": "Manager",
                    "prettySalary": "Tới $ 2,500 /tháng",
                    "approvedOn": "2026-06-30T14:42:33+07:00",
                    "expiredOn": "2026-07-30T23:59:59+07:00",
                    "workingLocations": [
                        {"cityName": "Ha Noi"},
                        {"cityName": "Ha Noi"},
                        {"cityName": "Ho Chi Minh"},
                    ],
                    "skills": [{"skillName": "Java"}, {"skillName": "PostgreSQL"}],
                    "jobDescription": "<p>Build distributed services and APIs.</p>",
                    "jobRequirement": "<p>At least four years of experience.</p>",
                }
            ],
        }
    )
    assert pages == 9
    assert len(jobs) == 1
    assert jobs[0].platform_job_id == "2073758"
    assert str(jobs[0].source_url) == (
        "https://www.vietnamworks.com/senior-software-engineer-2073758-jv"
    )
    assert jobs[0].location == ["Ha Noi", "Ho Chi Minh"]
    assert jobs[0].skills == ["Java", "PostgreSQL"]
    assert jobs[0].description == (
        "Build distributed services and APIs. At least four years of experience."
    )
    assert jobs[0].experience_years_min == 4
    assert jobs[0].experience_years_max is None
    assert jobs[0].job_level == "manager"
    assert jobs[0].salary_text == "Lên đến 2500 USD"
    assert jobs[0].posted_at == datetime.fromisoformat("2026-06-30T14:42:33+07:00")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"meta": {"code": 500, "nbPages": 1}, "data": []},
        {"meta": {"code": 200, "nbPages": "one"}, "data": []},
    ],
)
def test_parse_search_api_rejects_schema_drift(payload: object) -> None:
    with pytest.raises(ValueError, match="VietnamWorks"):
        parse_search_response(payload)


@pytest.mark.parametrize(
    ("currency", "salary_min", "salary_max"),
    [
        ("JPY", 100_000, 300_000),
        ("VND", 3_050_000_076_923, 0),
        ("USD", 0, 10_000),
    ],
)
def test_parse_search_api_discards_unsupported_or_implausible_salary(
    currency: str, salary_min: int, salary_max: int
) -> None:
    jobs, _ = parse_search_response(
        {
            "meta": {"code": 200, "nbPages": 1},
            "data": [
                {
                    "jobId": 1,
                    "jobTitle": "Software Engineer",
                    "companyName": "Example Co",
                    "isSalaryVisible": True,
                    "salaryCurrency": currency,
                    "salaryMin": salary_min,
                    "salaryMax": salary_max,
                    "approvedOn": "2026-07-01T08:00:00+07:00",
                    "expiredOn": "2026-08-01T08:00:00+07:00",
                }
            ],
        }
    )
    assert jobs[0].salary_text is None


def test_structured_vnd_salary_round_trips_without_scientific_notation() -> None:
    jobs, _ = parse_search_response(
        {
            "meta": {"code": 200, "nbPages": 1},
            "data": [
                {
                    "jobId": 2,
                    "jobTitle": "Backend Developer",
                    "companyName": "Example Co",
                    "isSalaryVisible": True,
                    "salaryCurrency": "VND",
                    "salaryMin": 15_000_000,
                    "salaryMax": 30_000_000,
                    "approvedOn": "2026-07-01T08:00:00+07:00",
                    "expiredOn": "2026-08-01T08:00:00+07:00",
                }
            ],
        }
    )
    assert jobs[0].salary_text == "15000000 - 30000000 VND"
    assert parse_salary(jobs[0].salary_text) == SalaryRange(15_000_000, 30_000_000, False)
