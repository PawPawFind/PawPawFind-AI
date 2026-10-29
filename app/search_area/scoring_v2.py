"""Distance-aware rules. V1 scoring remains in scoring.py unchanged."""

from app.schemas.search_area import BehaviorProfile, BehaviorType
from app.search_area.config import SEARCH_AREA_CONFIG, SearchAreaHeuristicConfig
from app.search_area.environment import EnvironmentData, EnvironmentKind
from app.search_area.geo import GridCell, distance_meters
from app.search_area.scoring import EnvironmentSpatialIndex, ScoreComponents, ScoredCell


def proximity(distance: float, radius: float) -> float:
    if radius <= 0:
        raise ValueError("환경 영향 반경은 양수여야 합니다.")
    return max(0.0, 1.0 - max(0.0, distance) / radius)


def score_grid_v2(
    cells: list[GridCell],
    search_radius_meters: int,
    behavior_type: BehaviorType,
    profile: BehaviorProfile,
    environment: EnvironmentData,
    config: SearchAreaHeuristicConfig = SEARCH_AREA_CONFIG,
) -> list[ScoredCell]:
    if not cells:
        return []
    if config.environment_influence_meters <= 0:
        raise ValueError("환경 영향 반경은 양수여야 합니다.")
    index = EnvironmentSpatialIndex(
        environment, cells[0].center, config.environment_bucket_size_meters
    )
    preferences = dict(dict(config.behavior_environment_preferences)[behavior_type.value])
    corridors = dict(config.corridor_preferences)
    penalties = dict(config.accessibility_penalties)
    result = []
    for cell in cells:
        # One strongest distance influence per kind; duplicate OSM features cannot stack.
        strengths: dict[EnvironmentKind, float] = {}
        for feature in index.nearby(cell.center, config.environment_influence_meters):
            strength = proximity(
                distance_meters(cell.center, feature.point), config.environment_influence_meters
            )
            if strength > 0:
                for kind in feature.kinds:
                    strengths[kind] = max(strengths.get(kind, 0.0), strength)
        behavior, behavior_kind = _strongest(strengths, preferences)
        corridor, corridor_kind = _strongest(strengths, corridors)
        accessibility = max(
            0.0,
            1
            - sum(penalties.get(kind.value, 0) * strength for kind, strength in strengths.items()),
        )
        components = ScoreComponents(
            distance=max(0.0, min(1.0, 1 - cell.distance_meters / search_radius_meters)),
            behavior_environment=behavior,
            corridor=corridor,
            accessibility=accessibility,
            event_context=_event_context(behavior_type, profile, strengths),
        )
        score = 100 * sum(
            getattr(components, name) * weight for name, weight in config.score_weights
        )
        result.append(
            ScoredCell(
                cell,
                max(0.0, min(100.0, score)),
                components,
                frozenset(strengths),
                behavior_kind,
                corridor_kind,
            )
        )
    return result


def _strongest(
    strengths: dict[EnvironmentKind, float], preferences: dict[str, float]
) -> tuple[float, EnvironmentKind | None]:
    values = sorted(
        ((preferences.get(kind.value, 0) * strength, kind) for kind, strength in strengths.items()),
        key=lambda pair: (-pair[0], pair[1]),
    )
    if not values or values[0][0] <= 0:
        return 0.0, None
    return min(1.0, values[0][0]), values[0][1]


def _event_context(
    behavior: BehaviorType, profile: BehaviorProfile, strengths: dict[EnvironmentKind, float]
) -> float:
    def near(kind: EnvironmentKind) -> float:
        return strengths.get(kind, 0.0)

    score = 0.5
    if behavior is BehaviorType.FEARFUL:
        score += 0.3 * (1 - near(EnvironmentKind.MAJOR_ROAD))
    elif behavior is BehaviorType.CHASE_DRIVEN:
        score += 0.3 * near(EnvironmentKind.FOOTPATH)
    elif behavior is BehaviorType.HUMAN_SEEKING:
        score += 0.3 * max(
            near(EnvironmentKind.COMMERCIAL), near(EnvironmentKind.BUILDING_RESIDENTIAL)
        )
    elif behavior is BehaviorType.ALOOF:
        score += 0.2 * near(EnvironmentKind.GREEN_SPACE)
    if profile.mobility.value == "LIMITED":
        score -= 0.3 * near(EnvironmentKind.RAILWAY_BARRIER)
    return max(0.0, min(1.0, score))
