import pytest

from app.schemas.search_area import BehaviorProfile, BehaviorType
from app.search_area.environment import EnvironmentData
from app.search_area.geo import GridCell
from app.search_area.scoring import (
    AreaCandidate,
    ScoreComponents,
    ScoredCell,
    candidate_contributions,
    cluster_scored_cells,
    rounded_contributions,
    score_grid,
    select_area_candidates,
)
from tests.test_search_area_golden import ORIGIN


def test_cluster_uses_actual_member_components():
    cells = score_grid(
        [GridCell(0, 0, ORIGIN, 0), GridCell(0, 1, ORIGIN, 200)],
        1000,
        BehaviorType.FEARFUL,
        BehaviorProfile(),
        EnvironmentData("TEST", ()),
    )
    candidate = cluster_scored_cells(cells)[0]
    assert len(candidate.cells) == 2
    assert candidate_contributions(candidate)["distance"] == pytest.approx(27)
    assert sum(rounded_contributions(candidate).values()) == candidate.priority_score


def test_representatives_use_selected_cell_components():
    from app.search_area.geo import generate_grid

    cells = score_grid(
        generate_grid(ORIGIN, 300),
        300,
        BehaviorType.FEARFUL,
        BehaviorProfile(),
        EnvironmentData("TEST", ()),
    )
    candidates = select_area_candidates(cells)
    assert len(candidates) == 2
    for candidate in candidates:
        assert len(candidate.cells) == 1
        assert candidate.cells[0].cell.center == candidate.center
        parts = rounded_contributions(candidate)
        assert sum(parts.values()) == candidate.priority_score
        assert all(
            0 <= value <= maximum for value, maximum in zip(parts.values(), [30, 30, 20, 10, 10])
        )


@pytest.mark.parametrize("raw,expected", [(0.5, 0), (1.5, 2), (2.5, 2)])
def test_bankers_rounding_and_deterministic_remainder_ties(raw, expected):
    # Equal .5 remainders: distance precedes behavior_environment.
    components = ScoreComponents(raw / 30, raw / 30, 0, 0, 0)
    cell = ScoredCell(GridCell(0, 0, ORIGIN, 0), raw * 2, components, frozenset())
    candidate = AreaCandidate(ORIGIN, 150, round(raw * 2), frozenset(), (cell,))
    parts = rounded_contributions(candidate)
    assert parts["distance"] == int(raw) + 1
    assert parts["behavior_environment"] == int(raw)
    assert sum(parts.values()) == candidate.priority_score
    # Single-component boundary preserves Python round used by V1.
    single = ScoredCell(cell.cell, raw, ScoreComponents(raw / 30, 0, 0, 0, 0), frozenset())
    assert (
        rounded_contributions(AreaCandidate(ORIGIN, 150, round(raw), frozenset(), (single,)))[
            "distance"
        ]
        == expected
    )
