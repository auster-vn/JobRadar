from starlette.requests import Request

from api.core.rate_limit import _limit_for, _must_fail_closed


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def test_dynamic_score_endpoint_is_rate_limited_and_fail_closed() -> None:
    request = _request("POST", "/api/jobs/00000000-0000-0000-0000-000000000001/score")

    assert _limit_for(request, authenticated=True) == (10, 60)
    assert _must_fail_closed(request)


def test_application_updates_are_rate_limited() -> None:
    request = _request("PATCH", "/api/applications/00000000-0000-0000-0000-000000000001")

    assert _limit_for(request, authenticated=True) == (30, 60)
    assert _must_fail_closed(request)


def test_canonical_contract_paths_share_api_rate_limits() -> None:
    login = _request("POST", "/auth/login")
    score = _request("POST", "/jobs/00000000-0000-0000-0000-000000000001/score")
    applications = _request("POST", "/applications")

    assert _limit_for(login, authenticated=False) == (5, 60)
    assert _limit_for(score, authenticated=True) == (10, 60)
    assert _limit_for(applications, authenticated=True) == (30, 60)
    assert _must_fail_closed(login)
    assert _must_fail_closed(score)
    assert _must_fail_closed(applications)
