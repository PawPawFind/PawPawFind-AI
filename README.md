# PawPawFind-AI
PawPawFind AI matching and recommended search area service

PawPawFind의 매칭 및 추천 검색 영역을 지원하는 FastAPI 기반 AI 서비스입니다.

## 기술 스택

- Python 3.12
- FastAPI
- uv
- pytest
- Ruff

## 개발 환경 설정

Python 3.12가 필요합니다. uv 설치 여부를 먼저 확인합니다.

```bash
uv --version
```

의존성과 개발 도구를 설치합니다.

```bash
uv sync --dev
```

## 애플리케이션 실행

```bash
uv run uvicorn app.main:app --reload
```

서버 실행 후 health endpoint를 확인합니다.

```bash
curl http://127.0.0.1:8000/health
```

정상 응답은 다음과 같습니다.

```json
{"status":"ok"}
```

## V11 위치·시간 재정렬

기존 `/match` 요청과 호환되며 다음 필드는 선택값입니다.

```json
{
  "reportId": 1,
  "species": "강아지",
  "photoUrls": ["https://example.com/query.jpg"],
  "features": [{"category": "털색", "keyword": "흰색"}],
  "reportType": "LOST",
  "eventDate": "2026-08-01",
  "latitude": 37.5665,
  "longitude": 126.9780,
  "happenPlace": "서울특별시 마포구",
  "description": null
}
```

후보에도 좌표가 있으면 `distanceKm`를 계산하고, 없으면 `happenPlace`의 행정구역을
비교합니다. 위치·시간 정보가 없으면 해당 가중치는 자동으로 제외됩니다. 모든 점수는
후보 정렬용이며 동일 개체 확률이 아닙니다. 메모리가 작은 서버에서는 자유문장 E5
재정렬을 기본적으로 비활성화합니다.

## 추천 수색 영역 API V1

`POST /search-areas`는 실종 강아지의 마지막 목격 정보와 행동 프로필을 바탕으로
카카오맵에 표시할 수 있는 중심 좌표와 반경을 최소 2개, 최대 3개 반환합니다.
3순위는 다른 추천 영역과 충분히 분리된 독립 유효 후보가 있을 때만 반환합니다.
`priorityScore`는
실제 발견 확률이 아니라 `HEURISTIC_V1`의 **수색 우선점수**입니다.

요청 예시:

```json
{
  "reportId": 1,
  "species": "강아지",
  "size": "중형",
  "eventDate": "2026-08-24",
  "eventHour": 13,
  "latitude": 37.5665,
  "longitude": 126.978,
  "happenPlace": "서울특별시 마포구",
  "description": "산책 중 큰 소리에 놀라 도망감",
  "behaviorProfile": {
    "activityLevel": "HIGH",
    "strangerResponse": "AVOID",
    "noiseSensitivity": "HIGH",
    "chaseTendency": "LOW",
    "mobility": "NORMAL",
    "escapeCause": "NOISE"
  }
}
```

응답 예시:

```json
{
  "reportId": 1,
  "algorithmVersion": "HEURISTIC_V1",
  "behaviorType": "FEARFUL",
  "estimatedRadiusMeters": 1375,
  "environmentSource": "OPENSTREETMAP_OVERPASS",
  "fallbackUsed": false,
  "assumptions": [],
  "areas": [
    {
      "rank": 1,
      "center": {"latitude": 37.568, "longitude": 126.976},
      "radiusMeters": 250,
      "priorityScore": 84,
      "reasonCodes": ["FEARFUL_HIDE", "GREEN_SPACE", "LOW_TRAFFIC"],
      "reason": "두려움이 강한 행동 특성 및 주변 녹지와 이동 가능 경로를 고려한 우선 수색 영역입니다."
    },
    {
      "rank": 2,
      "center": {"latitude": 37.5662, "longitude": 126.979},
      "radiusMeters": 150,
      "priorityScore": 78,
      "reasonCodes": ["FEARFUL_HIDE", "WALKING_CORRIDOR", "LOW_TRAFFIC"],
      "reason": "두려움이 강한 행동 특성 및 보행로와 연결된 이동 경로를 고려한 우선 수색 영역입니다."
    }
  ]
}
```

행동 유형은 추격 원인 또는 강한 추격 성향, 두려움 관련 특성, 사람 접근 성향 순으로
`CHASE_DRIVEN`, `FEARFUL`, `HUMAN_SEEKING`을 판정하고 나머지를 `ALOOF`로 분류합니다.
24시간 기준 반경은 소형 500m, 중형 1000m, 대형 1500m입니다. 경과 시간 배수는
6시간 이내 0.6, 24시간 이내 1.0, 72시간 이내 1.4, 이후 1.8입니다. 활동량은
LOW 0.8, MEDIUM 1.0, HIGH 1.25, UNKNOWN 1.0을 적용합니다. 이동 제한은 0.5,
소음 도주는 1.1, 추격 도주는 1.2를 추가로 곱하며 결과는 300~3000m로 제한합니다.
실종 시간이 없으면 Asia/Seoul 정오로 추정하고 그 사실을 `assumptions`에 기록합니다.

수색 범위는 약 200m 격자로 나누고 거리 0.30, 행동·환경 0.30, 이동 통로 0.20,
장애물·접근성 0.10, 실종 상황 0.10의 가중치로 점수를 계산합니다. 공원·녹지,
보행로, 수변, 주거·상업 환경은 행동 유형별로 다르게 반영하고 주요 도로와 철도는
접근성에 불리하게 반영합니다. 고득점 인접 격자를 군집화한 원의 반경은 150~500m이며,
서로 크게 겹치는 낮은 순위 영역을 제거합니다. 이 설정은 학습된 값이 아니라 향후
운영 데이터로 교체·보정할 수 있는 초기 불변 휴리스틱입니다.

환경 데이터는 OpenStreetMap Overpass API에서 수집합니다. URL은 `OVERPASS_API_URL`,
timeout(초)은 `OVERPASS_TIMEOUT_SECONDS`로 설정할 수 있습니다. timeout, HTTP 오류,
잘못된 JSON 또는 빈 데이터가 발생하면 요청 전체를 실패시키지 않고 마지막 목격 위치
중심의 핵심 수색 영역과 같은 중심의 더 넓은 확장 수색 영역 2개를 반환합니다. 이때
`fallbackUsed`는 `true`,
`environmentSource`는 `UNAVAILABLE`이며 `assumptions`와 `reasonCodes`에도 fallback
사실을 표시합니다.

V1은 강아지만 지원하며 실시간 교통, 날씨, 지형 고도나 실제 이동 경로를 사용하지
않습니다. 좌표 계산은 최대 3km 범위에 적합한 국소 평면 근사이므로 장거리 또는 극지방
계산에 사용하지 않아야 합니다. 후속 백엔드 연동에서는 실종 신고 식별자와 행동 프로필을
전달하고 반환된 WGS84 중심 좌표 및 미터 반경을 지도 원 오버레이로 표시해야 합니다.

## 테스트와 코드 품질 검사

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Ruff로 코드를 포맷하려면 다음 명령을 사용합니다.

```bash
uv run ruff format .
```
