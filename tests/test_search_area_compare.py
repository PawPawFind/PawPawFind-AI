import asyncio
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

import app.search_area.comparison as comparison_module
from app.api.search_area import get_search_area_service
from app.main import app
from app.search_area.comparison import compare_results
from app.search_area.environment import (
    OverpassEnvironmentProvider,
    StaticEnvironmentProvider,
)
from app.search_area.geo import GeoPoint, distance_meters
from app.services.search_area import SearchAreaRecommendationService
from tests.test_search_area_golden import (
    GOLDEN,
    NOW,
    ORIGIN,
    SCENARIOS,
    FailedProvider,
    scenario,
    v1_result,
)


class CountingProvider:
    def __init__(self, data):
        self.data = data
        self.calls = []

    async def fetch(self, center, radius_meters):
        self.calls.append((center, radius_meters))
        return self.data


def compare(name):
    request, data = scenario(name)
    provider = FailedProvider() if name == "fallback" else StaticEnvironmentProvider(data)
    return asyncio.run(SearchAreaRecommendationService(provider, lambda: NOW).compare(request))


@pytest.mark.parametrize("name", SCENARIOS)
def test_comparison_matches_v1_golden_and_has_real_breakdowns(name):
    import json

    response = compare(name)
    body = response.model_dump(by_alias=True, mode="json")
    baseline = body["baseline"]
    # New comparison metadata does not change any V1 wire fields.
    old = json.loads(GOLDEN.read_text())[name]
    if name != "fallback":
        assert baseline["assumptions"] == old["assumptions"]
    for key in old.keys() - {"reportId", "areas", "assumptions"}:
        assert baseline[key] == old[key]
    for original, explained in zip(old["areas"], baseline["areas"], strict=True):
        assert {k: v for k, v in explained.items() if k != "scoreBreakdown"} == original
    assert body["comparedAt"] == "2026-10-29T12:00:00+09:00"
    assert body["reportId"] == 1
    assert body["improved"]["algorithmVersion"] == "HEURISTIC_V2"
    for result in (body["baseline"], body["improved"]):
        assert result["behaviorType"] == baseline["behaviorType"]
        assert result["estimatedRadiusMeters"] == baseline["estimatedRadiusMeters"]
        assert result["environmentSource"] == baseline["environmentSource"]
        for area in result["areas"]:
            parts = area["scoreBreakdown"]
            if name == "fallback":
                assert parts is None
            else:
                assert set(parts) == {
                    "distance",
                    "behaviorEnvironment",
                    "corridor",
                    "accessibility",
                    "eventContext",
                }
                assert sum(parts.values()) == area["priorityScore"]
                for key, maximum in [
                    ("distance", 30),
                    ("behaviorEnvironment", 30),
                    ("corridor", 20),
                    ("accessibility", 10),
                    ("eventContext", 10),
                ]:
                    assert 0 <= parts[key] <= maximum
    assert baseline["assumptions"] == body["improved"]["assumptions"]


def test_preparation_clock_environment_and_algorithm_inputs_are_shared(monkeypatch):
    request, data = scenario("fearful_park")
    provider = CountingProvider(data)
    clock = Mock(return_value=NOW)
    v1 = Mock(wraps=comparison_module.score_grid)
    v2 = Mock(wraps=comparison_module.score_grid_v2)
    monkeypatch.setattr(comparison_module, "score_grid", v1)
    monkeypatch.setattr(comparison_module, "score_grid_v2", v2)
    classifier = Mock(wraps=comparison_module.classify_behavior)
    elapsed = Mock(wraps=comparison_module.calculate_elapsed_time)
    radius = Mock(wraps=comparison_module.calculate_search_radius)
    monkeypatch.setattr(comparison_module, "classify_behavior", classifier)
    monkeypatch.setattr(comparison_module, "calculate_elapsed_time", elapsed)
    monkeypatch.setattr(comparison_module, "calculate_search_radius", radius)
    response = asyncio.run(SearchAreaRecommendationService(provider, clock).compare(request))
    clock.assert_called_once_with()
    classifier.assert_called_once_with(request.behavior_profile)
    elapsed.assert_called_once_with(request, NOW)
    radius.assert_called_once()
    assert provider.calls == [(ORIGIN, response.baseline.estimated_radius_meters)]
    v1.assert_called_once()
    v2.assert_called_once()
    assert v1.call_args == v2.call_args
    assert v1.call_args.args[0] is v2.call_args.args[0]
    assert v1.call_args.args[3] is request.behavior_profile
    assert v1.call_args.args[4] is v2.call_args.args[4] is data


@pytest.mark.parametrize("failure", [None, "timeout", "http", "json", "empty"])
def test_overpass_is_called_once_with_mock_transport_and_shared_failure(failure):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "http":
            return httpx.Response(503)
        if failure == "json":
            return httpx.Response(200, content=b"invalid")
        return httpx.Response(
            200,
            json={
                "elements": []
                if failure == "empty"
                else [
                    {"lat": ORIGIN.latitude, "lon": ORIGIN.longitude, "tags": {"leisure": "park"}}
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await SearchAreaRecommendationService(
                OverpassEnvironmentProvider(client=client), lambda: NOW
            ).compare(scenario("fearful_park")[0])

    response = asyncio.run(run())
    assert len(calls) == 1
    assert response.baseline.fallback_used == response.improved.fallback_used == bool(failure)
    if failure:
        assert response.comparison.fallback_used
        assert "제한" in response.comparison.summary
        assert "평가할 수 없습니다" in response.comparison.summary
        assert response.baseline.areas == response.improved.areas
        assert all(area.score_breakdown is None for area in response.improved.areas)


def test_center_shift_score_deltas_and_missing_ranks():
    response = compare("active_path")
    for change in response.comparison.rank_changes:
        before = response.baseline.areas[change.rank - 1]
        after = response.improved.areas[change.rank - 1]
        expected = distance_meters(
            GeoPoint(**before.center.model_dump()), GeoPoint(**after.center.model_dump())
        )
        assert change.center_shift_meters == round(expected, 3)
        assert change.score_delta == after.priority_score - before.priority_score
        assert change.added_reason_codes == [
            code for code in after.reason_codes if code not in before.reason_codes
        ]
    short = response.improved.model_copy(update={"areas": response.improved.areas[:1]})
    removed = compare_results(response.baseline, short).rank_changes[-1]
    assert removed.status == "REMOVED"
    assert removed.after_center is removed.after_priority_score is removed.score_delta is None
    added = compare_results(short, response.baseline).rank_changes[-1]
    assert added.status == "ADDED"
    assert added.before_center is added.before_priority_score is added.center_shift_meters is None


@pytest.fixture
def api_client():
    request, data = scenario("fearful_park")
    provider = CountingProvider(data)
    clock = Mock(return_value=NOW)
    app.dependency_overrides[get_search_area_service] = lambda: SearchAreaRecommendationService(
        provider, clock
    )
    try:
        with TestClient(app) as client:
            yield client, request, provider, clock
    finally:
        app.dependency_overrides.pop(get_search_area_service, None)


def test_compare_api_contract_and_existing_endpoint_unchanged(api_client):
    client, request, provider, clock = api_client
    payload = request.model_dump(by_alias=True, mode="json")
    response = client.post("/search-areas/compare", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"reportId", "comparedAt", "baseline", "improved", "comparison"}
    assert body["baseline"]["algorithmVersion"] == "HEURISTIC_V1"
    assert body["improved"]["algorithmVersion"] == "HEURISTIC_V2"
    assert "scoreBreakdown" in body["baseline"]["areas"][0]
    assert len(provider.calls) == clock.call_count == 1
    old = client.post("/search-areas", json=payload)
    assert old.status_code == 200
    assert old.json() == v1_result("fearful_park")
    assert "scoreBreakdown" not in old.json()["areas"][0]
    assert "/search-areas/compare" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize(
    "update",
    [
        {"reportId": 0},
        {"species": "고양이"},
        {"size": "초대형"},
        {"eventHour": 24},
        {"latitude": 91},
        {"longitude": 181},
        {"eventDate": "2026-10-30"},
        {"behaviorProfile": {"noiseSensitivity": "WRONG"}},
    ],
)
def test_compare_api_invalid_input_422_without_environment_fetch(api_client, update):
    client, request, provider, clock = api_client
    payload = request.model_dump(by_alias=True, mode="json")
    payload.update(update)
    assert client.post("/search-areas/compare", json=payload).status_code == 422
    assert not provider.calls


def test_compare_api_fallback(api_client):
    client, request, _, _ = api_client
    app.dependency_overrides[get_search_area_service] = lambda: SearchAreaRecommendationService(
        FailedProvider(), lambda: NOW
    )
    response = client.post(
        "/search-areas/compare", json=request.model_dump(by_alias=True, mode="json")
    )
    assert response.status_code == 200
    assert response.json()["comparison"]["fallbackUsed"]
    assert response.json()["improved"]["areas"][0]["scoreBreakdown"] is None


def test_missing_hour_assumptions_are_identical(api_client):
    client, request, _, _ = api_client
    payload = request.model_dump(by_alias=True, mode="json")
    payload["eventHour"] = None
    response = client.post("/search-areas/compare", json=payload).json()
    assert response["baseline"]["assumptions"] == response["improved"]["assumptions"]
    assert response["baseline"]["assumptions"]
