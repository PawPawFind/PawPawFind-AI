import math
from dataclasses import dataclass

from app.schemas.search_area import BehaviorProfile, BehaviorType
from app.search_area.config import SEARCH_AREA_CONFIG, SearchAreaHeuristicConfig
from app.search_area.environment import EnvironmentData, EnvironmentFeature, EnvironmentKind
from app.search_area.geo import (
    GeoPoint,
    GridCell,
    coordinate_offset_to_meters,
    distance_meters,
)


@dataclass(frozen=True)
class ScoreComponents:
    distance: float
    behavior_environment: float
    corridor: float
    accessibility: float
    event_context: float


@dataclass(frozen=True)
class ScoredCell:
    cell: GridCell
    priority_score: float
    components: ScoreComponents
    nearby_kinds: frozenset[EnvironmentKind]


@dataclass(frozen=True)
class AreaCandidate:
    center: GeoPoint
    radius_meters: int
    priority_score: int
    kinds: frozenset[EnvironmentKind]


class EnvironmentSpatialIndex:
    def __init__(
        self,
        environment: EnvironmentData,
        reference: GeoPoint,
        bucket_size_meters: int,
    ) -> None:
        if bucket_size_meters <= 0:
            raise ValueError("환경 공간 버킷 크기는 양수여야 합니다.")
        self.environment = environment
        self.reference = reference
        self.bucket_size_meters = bucket_size_meters
        buckets: dict[tuple[int, int], list[EnvironmentFeature]] = {}
        for feature in environment.features:
            buckets.setdefault(self._bucket_key(feature.point), []).append(feature)
        self._buckets = {key: tuple(features) for key, features in buckets.items()}

    def nearby(self, point: GeoPoint, influence_meters: int) -> tuple[EnvironmentFeature, ...]:
        if influence_meters < 0:
            raise ValueError("환경 영향 반경은 음수일 수 없습니다.")
        center_row, center_column = self._bucket_key(point)
        bucket_extent = math.ceil(influence_meters / self.bucket_size_meters) + 1
        candidates = (
            feature
            for row in range(center_row - bucket_extent, center_row + bucket_extent + 1)
            for column in range(center_column - bucket_extent, center_column + bucket_extent + 1)
            for feature in self._buckets.get((row, column), ())
        )
        return tuple(
            feature
            for feature in candidates
            if distance_meters(point, feature.point) <= influence_meters
        )

    def _bucket_key(self, point: GeoPoint) -> tuple[int, int]:
        north, east = coordinate_offset_to_meters(
            point.latitude - self.reference.latitude,
            point.longitude - self.reference.longitude,
            self.reference.latitude,
        )
        return (
            math.floor(north / self.bucket_size_meters),
            math.floor(east / self.bucket_size_meters),
        )


def score_grid(
    cells: list[GridCell],
    search_radius_meters: int,
    behavior_type: BehaviorType,
    profile: BehaviorProfile,
    environment: EnvironmentData,
    config: SearchAreaHeuristicConfig = SEARCH_AREA_CONFIG,
) -> list[ScoredCell]:
    if not cells:
        return []
    spatial_index = EnvironmentSpatialIndex(
        environment, cells[0].center, config.environment_bucket_size_meters
    )
    return [
        _score_cell(cell, search_radius_meters, behavior_type, profile, spatial_index, config)
        for cell in cells
    ]


def _score_cell(
    cell: GridCell,
    search_radius_meters: int,
    behavior_type: BehaviorType,
    profile: BehaviorProfile,
    spatial_index: EnvironmentSpatialIndex,
    config: SearchAreaHeuristicConfig,
) -> ScoredCell:
    nearby = spatial_index.nearby(cell.center, config.environment_influence_meters)
    kinds = frozenset(kind for feature in nearby for kind in feature.kinds)
    distance_score = _clamp01(1 - cell.distance_meters / search_radius_meters)
    preferences = dict(dict(config.behavior_environment_preferences)[behavior_type.value])
    behavior_score = max((preferences.get(kind.value, 0.0) for kind in kinds), default=0.2)
    corridor_preferences = dict(config.corridor_preferences)
    corridor_score = max((corridor_preferences.get(kind.value, 0.0) for kind in kinds), default=0.1)
    penalties = dict(config.accessibility_penalties)
    accessibility_score = _clamp01(1.0 - sum(penalties.get(kind.value, 0.0) for kind in kinds))
    event_context_score = _event_context_score(behavior_type, profile, kinds)
    components = ScoreComponents(
        distance=distance_score,
        behavior_environment=_clamp01(behavior_score),
        corridor=_clamp01(corridor_score),
        accessibility=accessibility_score,
        event_context=event_context_score,
    )
    weights = dict(config.score_weights)
    final = 100 * sum(getattr(components, name) * weight for name, weight in weights.items())
    return ScoredCell(cell, _clamp(final, 0, 100), components, kinds)


def _event_context_score(
    behavior_type: BehaviorType,
    profile: BehaviorProfile,
    kinds: frozenset[EnvironmentKind],
) -> float:
    score = 0.5
    if behavior_type is BehaviorType.FEARFUL and EnvironmentKind.MAJOR_ROAD not in kinds:
        score += 0.3
    elif behavior_type is BehaviorType.CHASE_DRIVEN and EnvironmentKind.FOOTPATH in kinds:
        score += 0.3
    elif behavior_type is BehaviorType.HUMAN_SEEKING and (
        EnvironmentKind.COMMERCIAL in kinds or EnvironmentKind.BUILDING_RESIDENTIAL in kinds
    ):
        score += 0.3
    elif behavior_type is BehaviorType.ALOOF and EnvironmentKind.GREEN_SPACE in kinds:
        score += 0.2
    if profile.mobility.value == "LIMITED" and EnvironmentKind.RAILWAY_BARRIER in kinds:
        score -= 0.3
    return _clamp01(score)


def cluster_scored_cells(
    scored_cells: list[ScoredCell],
    config: SearchAreaHeuristicConfig = SEARCH_AREA_CONFIG,
) -> list[AreaCandidate]:
    if not scored_cells:
        return []
    top_score = max(item.priority_score for item in scored_cells)
    threshold = max(config.high_score_floor, top_score - config.high_score_band)
    eligible = {
        (item.cell.row, item.cell.column): item
        for item in scored_cells
        if item.priority_score >= threshold
    }
    clusters: list[list[ScoredCell]] = []
    while eligible:
        start = min(eligible)
        stack = [start]
        cluster: list[ScoredCell] = []
        while stack:
            key = stack.pop()
            item = eligible.pop(key, None)
            if item is None:
                continue
            cluster.append(item)
            row, column = key
            stack.extend(
                (row + row_delta, column + column_delta)
                for row_delta in (-1, 0, 1)
                for column_delta in (-1, 0, 1)
                if row_delta or column_delta
            )
        clusters.append(cluster)
    candidates = [_cluster_candidate(cluster, config) for cluster in clusters]
    return sorted(
        candidates,
        key=lambda item: (-item.priority_score, item.center.latitude, item.center.longitude),
    )


def _cluster_candidate(
    cluster: list[ScoredCell], config: SearchAreaHeuristicConfig
) -> AreaCandidate:
    total_weight = sum(item.priority_score for item in cluster)
    center = GeoPoint(
        latitude=sum(item.cell.center.latitude * item.priority_score for item in cluster)
        / total_weight,
        longitude=sum(item.cell.center.longitude * item.priority_score for item in cluster)
        / total_weight,
    )
    radius = round(
        config.cluster_radius_base_meters + config.grid_size_meters * math.sqrt(len(cluster)) / 2
    )
    radius = max(config.min_area_radius_meters, min(config.max_area_radius_meters, radius))
    kinds = frozenset(kind for item in cluster for kind in item.nearby_kinds)
    score = round(sum(item.priority_score for item in cluster) / len(cluster))
    return AreaCandidate(center, radius, score, kinds)


def remove_overlapping_candidates(
    candidates: list[AreaCandidate],
    config: SearchAreaHeuristicConfig = SEARCH_AREA_CONFIG,
) -> list[AreaCandidate]:
    selected: list[AreaCandidate] = []
    for candidate in sorted(candidates, key=lambda item: -item.priority_score):
        overlaps = any(_candidates_overlap(candidate, existing, config) for existing in selected)
        if not overlaps:
            selected.append(candidate)
        if len(selected) == config.max_areas:
            break
    return selected


def select_area_candidates(
    scored_cells: list[ScoredCell],
    config: SearchAreaHeuristicConfig = SEARCH_AREA_CONFIG,
) -> list[AreaCandidate]:
    """Prefer clustered candidates, splitting a lone cluster into local representatives."""
    clustered = cluster_scored_cells(scored_cells, config)
    selected = remove_overlapping_candidates(clustered, config)
    if len(selected) >= config.min_areas:
        return selected

    representatives: list[AreaCandidate] = []
    for item in sorted(
        scored_cells,
        key=lambda scored: (
            -scored.priority_score,
            scored.cell.row,
            scored.cell.column,
            scored.cell.center.latitude,
            scored.cell.center.longitude,
        ),
    ):
        candidate = AreaCandidate(
            center=item.cell.center,
            radius_meters=config.min_area_radius_meters,
            priority_score=round(item.priority_score),
            kinds=item.nearby_kinds,
        )
        if any(_candidates_overlap(candidate, existing, config) for existing in representatives):
            continue
        representatives.append(candidate)
        if len(representatives) == config.min_areas:
            return representatives
    return representatives


def _candidates_overlap(
    candidate: AreaCandidate,
    existing: AreaCandidate,
    config: SearchAreaHeuristicConfig,
) -> bool:
    return distance_meters(candidate.center, existing.center) < config.overlap_ratio * (
        candidate.radius_meters + existing.radius_meters
    )


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
