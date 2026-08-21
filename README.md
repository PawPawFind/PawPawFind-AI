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
