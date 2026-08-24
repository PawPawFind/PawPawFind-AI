import math
from dataclasses import dataclass

from app.search_area.config import SEARCH_AREA_CONFIG

EARTH_RADIUS_METERS = 6_371_008.8


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class GridCell:
    row: int
    column: int
    center: GeoPoint
    distance_meters: float


def meters_to_coordinate_offset(
    north_meters: float, east_meters: float, reference_latitude: float
) -> tuple[float, float]:
    latitude_delta = math.degrees(north_meters / EARTH_RADIUS_METERS)
    longitude_scale = math.cos(math.radians(reference_latitude))
    if abs(longitude_scale) < 1e-12:
        raise ValueError("극점에서는 경도 오프셋을 계산할 수 없습니다.")
    longitude_delta = math.degrees(east_meters / (EARTH_RADIUS_METERS * longitude_scale))
    return latitude_delta, longitude_delta


def coordinate_offset_to_meters(
    latitude_delta: float, longitude_delta: float, reference_latitude: float
) -> tuple[float, float]:
    north_meters = math.radians(latitude_delta) * EARTH_RADIUS_METERS
    east_meters = (
        math.radians(longitude_delta)
        * EARTH_RADIUS_METERS
        * math.cos(math.radians(reference_latitude))
    )
    return north_meters, east_meters


def offset_point(origin: GeoPoint, north_meters: float, east_meters: float) -> GeoPoint:
    latitude_delta, longitude_delta = meters_to_coordinate_offset(
        north_meters, east_meters, origin.latitude
    )
    return GeoPoint(
        latitude=origin.latitude + latitude_delta,
        longitude=origin.longitude + longitude_delta,
    )


def distance_meters(first: GeoPoint, second: GeoPoint) -> float:
    mean_latitude = (first.latitude + second.latitude) / 2
    north, east = coordinate_offset_to_meters(
        second.latitude - first.latitude,
        second.longitude - first.longitude,
        mean_latitude,
    )
    return math.hypot(north, east)


def generate_grid(
    origin: GeoPoint,
    radius_meters: int,
    cell_size_meters: int = SEARCH_AREA_CONFIG.grid_size_meters,
) -> list[GridCell]:
    if radius_meters <= 0 or cell_size_meters <= 0:
        raise ValueError("반경과 격자 크기는 양수여야 합니다.")
    extent = math.ceil(radius_meters / cell_size_meters)
    cells: list[GridCell] = []
    for row in range(-extent, extent + 1):
        for column in range(-extent, extent + 1):
            north = row * cell_size_meters
            east = column * cell_size_meters
            distance = math.hypot(north, east)
            if distance <= radius_meters:
                cells.append(
                    GridCell(
                        row=row,
                        column=column,
                        center=offset_point(origin, north, east),
                        distance_meters=distance,
                    )
                )
    return cells
