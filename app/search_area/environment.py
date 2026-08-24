from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import httpx

from app.search_area.config import SEARCH_AREA_CONFIG
from app.search_area.geo import GeoPoint


class EnvironmentKind(StrEnum):
    BUILDING_RESIDENTIAL = "BUILDING_RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    GREEN_SPACE = "GREEN_SPACE"
    FOOTPATH = "FOOTPATH"
    ROAD = "ROAD"
    MAJOR_ROAD = "MAJOR_ROAD"
    WATER = "WATER"
    RAILWAY_BARRIER = "RAILWAY_BARRIER"


@dataclass(frozen=True)
class EnvironmentFeature:
    point: GeoPoint
    kinds: frozenset[EnvironmentKind]


@dataclass(frozen=True)
class EnvironmentData:
    source: str
    features: tuple[EnvironmentFeature, ...]


class EnvironmentProviderError(RuntimeError):
    pass


class EnvironmentProvider(Protocol):
    async def fetch(self, center: GeoPoint, radius_meters: int) -> EnvironmentData: ...


@dataclass(frozen=True)
class StaticEnvironmentProvider:
    data: EnvironmentData

    async def fetch(self, center: GeoPoint, radius_meters: int) -> EnvironmentData:
        return self.data


class OverpassEnvironmentProvider:
    source = "OPENSTREETMAP_OVERPASS"

    def __init__(
        self,
        url: str = "https://overpass-api.de/api/interpreter",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def fetch(self, center: GeoPoint, radius_meters: int) -> EnvironmentData:
        bounded_radius = min(radius_meters, SEARCH_AREA_CONFIG.max_search_radius_meters)
        if bounded_radius <= 0:
            raise ValueError("조회 반경은 양수여야 합니다.")
        query = self._build_query(center, bounded_radius)
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(self.url, data={"data": query})
            else:
                response = await self._client.post(self.url, data={"data": query})
            response.raise_for_status()
            payload = response.json()
        except (httpx.TimeoutException, httpx.HTTPError, ValueError) as exc:
            raise EnvironmentProviderError("Overpass 환경 데이터를 가져오지 못했습니다.") from exc
        data = parse_overpass_response(payload)
        if not data.features:
            raise EnvironmentProviderError("Overpass 환경 데이터가 비어 있습니다.")
        return data

    @staticmethod
    def _build_query(center: GeoPoint, radius_meters: int) -> str:
        around = f"around:{radius_meters},{center.latitude},{center.longitude}"
        return (
            "[out:json];("
            f'nwr["building"]({around});'
            f'nwr["landuse"]({around});'
            f'nwr["leisure"]({around});'
            f'nwr["highway"]({around});'
            f'nwr["natural"="water"]({around});'
            f'nwr["waterway"]({around});'
            f'nwr["railway"]({around});'
            f'nwr["barrier"]({around});'
            ");out center tags;"
        )


def parse_overpass_response(payload: object) -> EnvironmentData:
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise EnvironmentProviderError("Overpass 응답 형식이 올바르지 않습니다.")
    features: list[EnvironmentFeature] = []
    for element in payload["elements"]:
        if not isinstance(element, dict):
            continue
        point = _element_point(element)
        tags = element.get("tags")
        if point is None or not isinstance(tags, dict):
            continue
        kinds = _classify_tags(tags)
        if kinds:
            features.append(EnvironmentFeature(point=point, kinds=frozenset(kinds)))
    return EnvironmentData(source=OverpassEnvironmentProvider.source, features=tuple(features))


def _element_point(element: dict[str, object]) -> GeoPoint | None:
    latitude = element.get("lat")
    longitude = element.get("lon")
    center = element.get("center")
    if isinstance(center, dict):
        latitude = center.get("lat", latitude)
        longitude = center.get("lon", longitude)
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    return GeoPoint(float(latitude), float(longitude))


def _classify_tags(tags: dict[str, object]) -> set[EnvironmentKind]:
    kinds: set[EnvironmentKind] = set()
    landuse = tags.get("landuse")
    highway = tags.get("highway")
    if "building" in tags or landuse in {"residential"}:
        kinds.add(EnvironmentKind.BUILDING_RESIDENTIAL)
    if landuse in {"commercial", "retail"} or "shop" in tags:
        kinds.add(EnvironmentKind.COMMERCIAL)
    if landuse in {"forest", "grass", "meadow"} or tags.get("leisure") in {"park", "garden"}:
        kinds.add(EnvironmentKind.GREEN_SPACE)
    if highway in {"footway", "path", "pedestrian", "track"}:
        kinds.add(EnvironmentKind.FOOTPATH)
    elif highway in {"motorway", "trunk", "primary", "secondary"}:
        kinds.add(EnvironmentKind.MAJOR_ROAD)
    elif highway is not None:
        kinds.add(EnvironmentKind.ROAD)
    if tags.get("natural") == "water" or "waterway" in tags:
        kinds.add(EnvironmentKind.WATER)
    if "railway" in tags or "barrier" in tags:
        kinds.add(EnvironmentKind.RAILWAY_BARRIER)
    return kinds
