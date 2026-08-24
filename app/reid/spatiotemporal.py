"""Location and time consistency scoring for lost/found pet candidates."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Mapping

import numpy as np

from app.reid.config import LOCATION_DECAY_KM


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def compact_token(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", text_value(value)).strip()
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", normalized).lower()


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_report_type(value: Any, default: str) -> str:
    normalized = compact_token(value).upper()
    aliases = {
        "LOST": "LOST",
        "실종": "LOST",
        "찾고있어요": "LOST",
        "FOUND": "FOUND",
        "SIGHTING": "FOUND",
        "목격": "FOUND",
        "발견": "FOUND",
    }
    return aliases.get(normalized, default)


def parse_flexible_date(value: Any) -> date | None:
    raw = text_value(value)
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0088
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2.0) ** 2
    )
    return earth_radius_km * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1.0 - a, 0.0)))


def address_units(address: Any) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text_value(address))
    pattern = r"[가-힣0-9]+(?:특별자치도|특별자치시|특별시|광역시|도|시|군|구|읍|면|동|리)"
    return list(dict.fromkeys(re.findall(pattern, normalized)))


def address_unit_level(unit: str) -> str:
    if unit.endswith(("특별자치도", "특별자치시", "특별시", "광역시", "도")):
        return "province"
    if unit.endswith("시"):
        return "city"
    if unit.endswith(("군", "구")):
        return "district"
    return "local"


def address_units_by_level(address: Any) -> dict[str, set[str]]:
    levels = {"province": set(), "city": set(), "district": set(), "local": set()}
    for unit in address_units(address):
        levels[address_unit_level(unit)].add(unit)
    return levels


def address_location_similarity(query_address: Any, candidate_address: Any) -> float | None:
    query_levels = address_units_by_level(query_address)
    candidate_levels = address_units_by_level(candidate_address)
    if not any(query_levels.values()) or not any(candidate_levels.values()):
        return None

    def conflicts(level: str) -> bool:
        query_units = query_levels[level]
        candidate_units = candidate_levels[level]
        return bool(query_units and candidate_units and query_units.isdisjoint(candidate_units))

    # A shared name such as "중앙동" or "중구" is meaningful only when its
    # available parent areas do not contradict each other.
    if conflicts("province"):
        return 0.10

    shared_province = query_levels["province"] & candidate_levels["province"]
    shared_city = query_levels["city"] & candidate_levels["city"]
    shared_district = query_levels["district"] & candidate_levels["district"]
    shared_local = query_levels["local"] & candidate_levels["local"]
    parent_shared = bool(shared_province or shared_city or shared_district)
    parent_conflict = any(conflicts(level) for level in ("city", "district"))

    if shared_local and parent_shared and not parent_conflict:
        return 0.90
    if shared_district and not conflicts("city"):
        return 0.70
    if shared_province or shared_city or shared_local:
        return 0.40
    return 0.10


def location_similarity(
    query_metadata: Mapping[str, Any],
    candidate_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    query_lat = optional_float(query_metadata.get("latitude"))
    query_lng = optional_float(query_metadata.get("longitude"))
    candidate_lat = optional_float(candidate_metadata.get("latitude"))
    candidate_lng = optional_float(candidate_metadata.get("longitude"))
    valid_coordinates = (
        query_lat is not None
        and query_lng is not None
        and candidate_lat is not None
        and candidate_lng is not None
        and -90.0 <= query_lat <= 90.0
        and -90.0 <= candidate_lat <= 90.0
        and -180.0 <= query_lng <= 180.0
        and -180.0 <= candidate_lng <= 180.0
    )
    if valid_coordinates:
        distance = haversine_km(query_lat, query_lng, candidate_lat, candidate_lng)
        score = math.exp(-distance / max(LOCATION_DECAY_KM, 1e-6))
        return {
            "score": float(np.clip(score, 0.0, 1.0)),
            "distance_km": float(distance),
            "method": "coordinates",
        }

    address_score = address_location_similarity(
        query_metadata.get("address"), candidate_metadata.get("address")
    )
    return {
        "score": address_score,
        "distance_km": None,
        "method": "address_units" if address_score is not None else "unavailable",
    }


def time_similarity(
    query_metadata: Mapping[str, Any],
    candidate_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    query_date = parse_flexible_date(query_metadata.get("lost_at"))
    candidate_date = parse_flexible_date(candidate_metadata.get("found_at"))
    if query_date is None or candidate_date is None:
        return {"score": None, "elapsed_days": None}

    query_type = canonical_report_type(query_metadata.get("report_type"), default="LOST")
    candidate_type = canonical_report_type(candidate_metadata.get("report_type"), default="FOUND")
    if query_type == candidate_type:
        return {"score": None, "elapsed_days": None}
    if query_type == "FOUND" and candidate_type == "LOST":
        lost_date, found_date = candidate_date, query_date
    else:
        lost_date, found_date = query_date, candidate_date

    elapsed_days = (found_date - lost_date).days
    if elapsed_days < -1:
        score = 0.05
    elif elapsed_days < 0:
        score = 0.50
    elif elapsed_days <= 3:
        score = 1.00
    elif elapsed_days <= 14:
        score = 0.90
    elif elapsed_days <= 30:
        score = 0.75
    elif elapsed_days <= 90:
        score = 0.55
    elif elapsed_days <= 180:
        score = 0.35
    else:
        score = 0.20
    return {"score": score, "elapsed_days": elapsed_days}


def spatiotemporal_similarity(
    query_metadata: Mapping[str, Any],
    candidate_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    location = location_similarity(query_metadata, candidate_metadata)
    temporal = time_similarity(query_metadata, candidate_metadata)
    available: list[tuple[float, float]] = []
    if location["score"] is not None:
        available.append((0.65, float(location["score"])))
    if temporal["score"] is not None:
        available.append((0.35, float(temporal["score"])))

    score: float | None = None
    if available:
        total_weight = sum(weight for weight, _ in available)
        score = sum(weight * value for weight, value in available) / total_weight
    return {
        "score": score,
        "location_score": location["score"],
        "time_score": temporal["score"],
        "distance_km": location["distance_km"],
        "elapsed_days": temporal["elapsed_days"],
        "location_method": location["method"],
    }
