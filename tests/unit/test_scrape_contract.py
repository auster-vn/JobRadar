from workers.scrape_tasks import _result


def test_scrape_result_has_stable_production_contract() -> None:
    result = _result(
        "topcv",
        "partial",
        12,
        ["job-3:ValueError"],
        jobs_new=7,
        jobs_updated=4,
    )

    assert result == {
        "source": "topcv",
        "status": "partial",
        "jobs_found": 12,
        "errors": ["job-3:ValueError"],
        "jobs_new": 7,
        "jobs_updated": 4,
    }
