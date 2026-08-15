import pytest

from api import main


@pytest.mark.asyncio
async def test_version_identifies_the_running_source_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(main.settings, "source_revision", revision)

    payload = await main.version()

    assert payload == {
        "version": "0.1.0",
        "environment": main.settings.app_env,
        "source_revision": revision,
    }
