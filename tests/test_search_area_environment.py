from urllib.parse import parse_qs

import httpx
import pytest

from app.search_area.environment import (
    EnvironmentKind,
    EnvironmentProviderError,
    OverpassEnvironmentProvider,
    parse_overpass_response,
)
from app.search_area.geo import GeoPoint


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_parse_overpass_response_classifies_supported_features() -> None:
    data = parse_overpass_response(
        {
            "elements": [
                {"type": "node", "lat": 37.5, "lon": 127.0, "tags": {"leisure": "park"}},
                {
                    "type": "way",
                    "center": {"lat": 37.501, "lon": 127.001},
                    "tags": {"highway": "primary", "railway": "rail"},
                },
                {"type": "node", "lat": 37.502, "lon": 127.002, "tags": {"highway": "path"}},
            ]
        }
    )

    assert data.source == "OPENSTREETMAP_OVERPASS"
    assert data.features[0].kinds == {EnvironmentKind.GREEN_SPACE}
    assert data.features[1].kinds == {
        EnvironmentKind.MAJOR_ROAD,
        EnvironmentKind.RAILWAY_BARRIER,
    }
    assert data.features[2].kinds == {EnvironmentKind.FOOTPATH}


@pytest.mark.parametrize(
    "barrier", ["wall", "fence", "retaining_wall", "city_wall", "hedge", "guard_rail"]
)
def test_blocking_barriers_are_classified_as_movement_barriers(barrier: str) -> None:
    data = parse_overpass_response(
        {"elements": [{"lat": 37.5, "lon": 127.0, "tags": {"barrier": barrier}}]}
    )
    assert data.features[0].kinds == {EnvironmentKind.RAILWAY_BARRIER}


@pytest.mark.parametrize("barrier", ["gate", "lift_gate", "bollard", "kerb"])
def test_passage_facilities_are_not_classified_as_railway_barriers(barrier: str) -> None:
    data = parse_overpass_response(
        {"elements": [{"lat": 37.5, "lon": 127.0, "tags": {"barrier": barrier}}]}
    )
    assert data.features == ()


@pytest.mark.parametrize("payload", [None, {}, {"elements": "invalid"}])
def test_parse_overpass_response_rejects_invalid_shape(payload: object) -> None:
    with pytest.raises(EnvironmentProviderError):
        parse_overpass_response(payload)


@pytest.mark.anyio
async def test_provider_uses_bounded_radius_and_parses_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.content.decode())["data"][0]
        assert "around:3000" in query
        assert "[timeout:10]" in query
        assert "[maxsize:10000000]" in query
        assert '["highway"~"^(footway|path|pedestrian|track|' in query
        assert 'service|road)$"]' in query
        assert 'nwr["highway"]' not in query
        return httpx.Response(
            200,
            json={"elements": [{"lat": 37.5, "lon": 127.0, "tags": {"building": "yes"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OverpassEnvironmentProvider(client=client)
        data = await provider.fetch(GeoPoint(37.5, 127.0), 5000)

    assert data.features[0].kinds == {EnvironmentKind.BUILDING_RESIDENTIAL}


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["timeout", "http", "json", "empty"])
async def test_provider_normalizes_failures(failure: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "http":
            return httpx.Response(503)
        if failure == "json":
            return httpx.Response(200, content=b"not-json")
        return httpx.Response(200, json={"elements": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OverpassEnvironmentProvider(client=client)
        with pytest.raises(EnvironmentProviderError):
            await provider.fetch(GeoPoint(37.5, 127.0), 1000)
