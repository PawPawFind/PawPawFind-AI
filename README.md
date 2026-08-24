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
