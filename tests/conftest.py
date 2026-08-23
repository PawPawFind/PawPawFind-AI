import pytest


@pytest.fixture(autouse=True)
def _use_mock_match_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAWPAWFIND_MATCH_MODE", "mock")
