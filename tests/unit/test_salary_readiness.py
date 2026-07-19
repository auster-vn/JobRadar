from datetime import date

from ml.salary.readiness import assess_salary_data_readiness


def _row(index: int, month: int, role: str, location: str) -> dict[str, object]:
    return {
        "source_key": f"source:{index}",
        "source_snapshot_date": date(2026, month, 1),
        "title_normalized": role,
        "job_level": "mid",
        "location": location,
        "salary_currency": "VND",
    }


def test_salary_data_readiness_passes_complete_temporal_dataset() -> None:
    segments = [
        ("Backend Developer", "Ha Noi"),
        ("Data Engineer", "Ho Chi Minh"),
        ("Frontend Developer", "Da Nang"),
        ("Mobile Developer", "Ha Noi"),
        ("QA Engineer", "Ho Chi Minh"),
    ]
    rows = [
        _row(
            index=(month - 1) * 200 + index,
            month=month,
            role=segments[index % len(segments)][0],
            location=segments[index % len(segments)][1],
        )
        for month in range(1, 7)
        for index in range(200)
    ]

    report = assess_salary_data_readiness(rows)

    assert report["ready"] is True
    assert report["sample_size"] == 1200
    assert report["distinct_months"] == 6
    assert report["canonical_technical_rows"] == 1200
    assert report["final_month"] == "2026-06"
    assert report["final_month_rows"] == 200
    assert report["qualified_segments"] == 5
    assert len(report["supported_segments"]) == 5
    assert report["underqualified_segments"] == []
    assert all(requirement["passed"] for requirement in report["requirements"])


def test_salary_data_readiness_explains_incomplete_snapshot() -> None:
    rows = [_row(index, 1, "Backend Developer", "Ha Noi") for index in range(50)]
    rows.append({**rows[0], "salary_currency": "USD"})

    report = assess_salary_data_readiness(rows)
    requirements = {item["id"]: item for item in report["requirements"]}

    assert report["ready"] is False
    assert report["duplicate_source_keys"] == 1
    assert report["non_vnd_rows"] == 1
    assert requirements["distinct_months"]["passed"] is False
    assert requirements["canonical_technical_rows"]["passed"] is False
    assert requirements["supported_segments"]["passed"] is False
    assert requirements["final_month_rows"]["passed"] is False
    assert requirements["duplicate_source_keys"]["passed"] is False
    assert requirements["non_vnd_rows"]["passed"] is False


def test_salary_data_readiness_normalizes_primary_city_aliases() -> None:
    rows = [
        _row(index, 1 + index // 10, "Backend Developer", "Hồ Chí Minh (mới)")
        for index in range(30)
    ]

    report = assess_salary_data_readiness(rows)

    assert report["qualified_segments"] == 1
    assert report["segment_candidates"] == 1
    assert report["underqualified_segments"] == []


def test_salary_data_readiness_derives_supported_segments_from_training_only() -> None:
    segments = [
        "Backend Developer",
        "Data Engineer",
        "Frontend Developer",
        "Mobile Developer",
        "QA Engineer",
    ]
    rows = [
        _row(month * 1000 + role_index * 100 + index, month, role, "Ha Noi")
        for month in range(1, 7)
        for role_index, role in enumerate(segments)
        for index in range(40)
    ]
    training_rows = [row for row in rows if row["title_normalized"] != "QA Engineer"]

    report = assess_salary_data_readiness(rows, segment_rows=training_rows)

    assert report["ready"] is False
    assert report["qualified_segments"] == 4
    assert {segment["role"] for segment in report["supported_segments"]} == set(segments[:-1])
