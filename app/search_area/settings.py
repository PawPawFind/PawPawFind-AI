import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchAreaSettings:
    overpass_api_url: str
    overpass_timeout_seconds: float


def load_search_area_settings() -> SearchAreaSettings:
    raw_timeout = os.getenv("OVERPASS_TIMEOUT_SECONDS", "10")
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise ValueError("OVERPASS_TIMEOUT_SECONDS는 양수인 숫자여야 합니다.") from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("OVERPASS_TIMEOUT_SECONDS는 0보다 큰 유한한 숫자여야 합니다.")
    return SearchAreaSettings(
        overpass_api_url=os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter"),
        overpass_timeout_seconds=timeout_seconds,
    )
