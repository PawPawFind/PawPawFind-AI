import pytest

from app.search_area.geo import (
    GeoPoint,
    coordinate_offset_to_meters,
    distance_meters,
    generate_grid,
    meters_to_coordinate_offset,
    offset_point,
)


def test_meter_coordinate_conversion_round_trip() -> None:
    latitude_delta, longitude_delta = meters_to_coordinate_offset(200, -350, 37.5665)
    north, east = coordinate_offset_to_meters(latitude_delta, longitude_delta, 37.5665)

    assert north == pytest.approx(200)
    assert east == pytest.approx(-350)


def test_offset_point_preserves_requested_local_distance() -> None:
    origin = GeoPoint(37.5665, 126.978)
    moved = offset_point(origin, 300, 400)

    assert distance_meters(origin, moved) == pytest.approx(500, rel=1e-4)


def test_generate_grid_is_deterministic_and_bounded() -> None:
    origin = GeoPoint(37.5665, 126.978)
    first = generate_grid(origin, radius_meters=400, cell_size_meters=200)
    second = generate_grid(origin, radius_meters=400, cell_size_meters=200)

    assert first == second
    assert len(first) == 13
    assert first[0].row == -2
    assert all(cell.distance_meters <= 400 for cell in first)
    assert any(cell.row == 0 and cell.column == 0 and cell.center == origin for cell in first)


@pytest.mark.parametrize(("radius", "cell_size"), [(0, 200), (300, 0), (-1, 200)])
def test_generate_grid_rejects_non_positive_dimensions(radius: int, cell_size: int) -> None:
    with pytest.raises(ValueError):
        generate_grid(GeoPoint(37.5, 127.0), radius, cell_size)
