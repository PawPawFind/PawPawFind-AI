from dataclasses import dataclass


@dataclass(frozen=True)
class SearchAreaHeuristicConfig:
    """Replaceable initial heuristics; these values are not learned parameters."""

    algorithm_version: str = "HEURISTIC_V1"
    grid_size_meters: int = 200
    min_search_radius_meters: int = 300
    max_search_radius_meters: int = 3000
    min_area_radius_meters: int = 150
    max_area_radius_meters: int = 500
    max_areas: int = 3
    environment_influence_meters: int = 300
    high_score_floor: float = 50.0
    high_score_band: float = 12.0
    cluster_radius_base_meters: int = 100
    overlap_ratio: float = 0.6
    blocking_barrier_values: tuple[str, ...] = (
        "wall",
        "fence",
        "retaining_wall",
        "city_wall",
        "hedge",
        "guard_rail",
    )
    base_radius_by_size: tuple[tuple[str, int], ...] = (
        ("소형", 500),
        ("중형", 1000),
        ("대형", 1500),
    )
    elapsed_time_multipliers: tuple[tuple[float, float], ...] = (
        (6.0, 0.6),
        (24.0, 1.0),
        (72.0, 1.4),
        (float("inf"), 1.8),
    )
    activity_multipliers: tuple[tuple[str, float], ...] = (
        ("LOW", 0.8),
        ("MEDIUM", 1.0),
        ("HIGH", 1.25),
        ("UNKNOWN", 1.0),
    )
    limited_mobility_multiplier: float = 0.5
    noise_escape_multiplier: float = 1.1
    chase_escape_multiplier: float = 1.2
    score_weights: tuple[tuple[str, float], ...] = (
        ("distance", 0.30),
        ("behavior_environment", 0.30),
        ("corridor", 0.20),
        ("accessibility", 0.10),
        ("event_context", 0.10),
    )
    behavior_environment_preferences: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = (
        ("HUMAN_SEEKING", (("COMMERCIAL", 1.0), ("BUILDING_RESIDENTIAL", 0.8), ("FOOTPATH", 0.7))),
        ("FEARFUL", (("GREEN_SPACE", 1.0), ("BUILDING_RESIDENTIAL", 0.8), ("COMMERCIAL", 0.2))),
        ("CHASE_DRIVEN", (("GREEN_SPACE", 0.9), ("FOOTPATH", 1.0), ("WATER", 0.7))),
        ("ALOOF", (("GREEN_SPACE", 0.8), ("BUILDING_RESIDENTIAL", 0.6), ("FOOTPATH", 0.5))),
    )
    corridor_preferences: tuple[tuple[str, float], ...] = (
        ("FOOTPATH", 1.0),
        ("GREEN_SPACE", 0.7),
        ("WATER", 0.7),
        ("ROAD", 0.3),
    )
    accessibility_penalties: tuple[tuple[str, float], ...] = (
        ("MAJOR_ROAD", 0.7),
        ("RAILWAY_BARRIER", 0.8),
        ("ROAD", 0.2),
    )


SEARCH_AREA_CONFIG = SearchAreaHeuristicConfig()
