from api.main import app


def test_required_canonical_api_contract_is_exposed() -> None:
    paths = app.openapi()["paths"]

    assert "get" in paths["/health"]
    assert "post" in paths["/auth/login"]
    assert "get" in paths["/jobs"]
    assert "get" in paths["/jobs/{job_id}"]
    assert "post" in paths["/jobs/{job_id}/score"]
    assert set(paths["/applications"]) == {"get", "post"}
    assert "get" in paths["/profile"]


def test_daily_pipeline_requires_a_secret_in_openapi() -> None:
    operation = app.openapi()["paths"]["/api/cron/daily"]["post"]
    parameters = operation["parameters"]

    assert any(parameter["name"] == "X-Cron-Secret" for parameter in parameters)
