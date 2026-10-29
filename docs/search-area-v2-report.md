# 수색 영역 V2 구현 결과

## 작업 위치와 Git

- AI 저장소: `/Users/kimgayoon/IdeaProjects/PawPawFind-AI`
- 별도 작업 트리: `/private/tmp/pawpawfind-ai-v2`
- 작업 브랜치: `feat/search-area-v2-explain-compare`
- 시작 HEAD: `ef43a3a` (fetch 후 최신 origin/develop)
- 원래 AI 체크아웃은 `fix/search-area-min-two-ranks`, `80f6010`에서 보존했다.
- 미커밋 변경은 없었고 원래 브랜치의 수정은 최신 develop에 #19로 병합되어 있었다.
- AI 저장소 및 상위 적용 경로에서 AGENTS.md와 CONTRIBUTING.md는 발견되지 않았다.
- Backend와 Frontend 파일을 수정하지 않았다. push, PR, merge, 배포를 수행하지 않았다.
- 종료 HEAD와 전체 로컬 커밋 목록은 최종 응답 및 `git log`로 확인할 수 있다.

## 변경 파일

| 파일 | 변경 목적 |
| --- | --- |
| README.md | V2와 비교 API 안내 |
| app/api/search_area.py | 비교 route 추가, 기존 DI 및 422 처리 재사용 |
| app/schemas/search_area.py | 비교 전용 camelCase DTO와 nullable breakdown |
| app/services/search_area.py | compare 진입점 추가; recommend 구현 보존 |
| app/search_area/scoring.py | 구성 격자 추적 및 실제 점수 기여도 집계·정수화 |
| app/search_area/scoring_v2.py | V1과 분리한 거리 기반 계산 |
| app/search_area/explanations.py | V2 실제 점수와 선정 환경에 근거한 설명 |
| app/search_area/comparison.py | 단일 준비·조회 후 두 버전 계산과 순위별 차이 |
| tests/test_search_area_golden.py | 고정 입력/환경/시각 V1 전체 응답 회귀 |
| tests/fixtures/search_area_v1.json | 변경 전 V1 전체 응답 6가지 |
| tests/test_search_area_breakdown.py | 군집·대표 격자·반올림·범위 |
| tests/test_search_area_v2.py | 거리·행동·통로·장애물·희소 환경·정렬 |
| tests/test_search_area_compare.py | 공정한 비교, API, 단일 조회, 오류와 fallback |
| tests/test_search_area_explanations.py | 실제 점수·환경 근거, 보수적 문구 |
| docs/search-area-v2.md | 알고리즘 및 Backend/Frontend 계약 |
| docs/examples/search-area-compare-request.json | 실제 TestClient 실행 요청 |
| docs/examples/search-area-compare-response.json | 실제 TestClient 실행 전체 응답 |
| docs/search-area-v2-report.md | 이 결과 보고 |

`config.py`의 기존 환경 반경·선호도·가중치를 재사용했다.
settings, environment provider, geo, heuristics 및 의존성 파일은 변경하지 않았다.

## 보존한 V1 및 신규 구현

V1 점수식, 행동 분류, 예상 반경, 환경 선호도, 군집화·대표 격자 선정,
중복 제거, 순위, 좌표 반올림, 기존 reason/reasonCodes, fallback과
`POST /search-areas` 응답 계약을 유지했다. 기존 테스트를 수정하지 않았다.

V2는 환경 종류별 가장 가까운 대표점에서 `max(0, 1-d/R)` 영향도를 계산한다.
행동·환경 및 통로 선호도에 영향도를 곱한 최댓값을 사용한다. 장애물 감점도 거리에
비례해 감소하며 같은 환경 종류를 중복 가산하지 않는다. 상황 점수는 기존 행동별
의미를 보존하면서 환경 조건을 거리 감쇠로 연속화한다. 최종 가중치는 동일하다.

후보는 실제 구성 격자들을 추적한다. 기여점수는 항목별 산술평균 × 가중치 × 100이다.
기존 priorityScore의 Python round 결과를 보존하고 최대 잔여 방식으로 표시용 정수를
배분한다. 동률은 설정 항목 순서다. 합은 priorityScore와 같다. fallback은 null이다.

V2 설명은 실제 양수 기여점수 순으로 선택하며, 격자에서 실제 최댓값을 만든 환경을
추적해 근거 없는 환경을 설명하지 않는다. 환경 근거가 적으면 제한 안내를 붙인다.
LOW_TRAFFIC은 V2에서 생성하지 않는다. V1 문구는 호환성을 위해 유지한다.

자세한 계산식·반올림·상황 점수 변경 이유는 [API 문서](search-area-v2.md)에 있다.

## 실제 V1/V2 결과

기준 시각 `2026-10-29T12:00:00+09:00`, 각 시나리오의 고정 환경에서 실행했다.
점수 목록의 순서는 rank 순서다. 중심 이동은 응답 좌표 사이의 미터 거리다.

| 시나리오 | V1 우선점수 | V2 우선점수 | 동일 순위 중심 이동(m) |
| --- | --- | --- | --- |
| A. 소음 민감 + 북쪽 75m 녹지 | 92, 86 | 81, 68 | 0, 400.080 |
| B. 높은 활동량·추격 + 보행로 | 98, 93 | 94, 70 | 0, 400.080 |
| C. 가까운 주요 도로·철도 장벽 | 32, 29 | 33, 30 | 0, 199.929 |
| D. 희소 환경: 290m 주거 대표점 | 72, 66 | 58, 50 | 200.040, 199.929 |
| 추가: 성공한 빈 Static 환경 | 53, 47 | 45, 39 | 0, 0 |
| E. 환경 제공자 실패 | 50, 40 | 50, 40 | 0, 0 |

Overpass의 실제 빈 응답은 provider 오류로 정규화되어 E와 같은 fallback이다.
빈 Static 환경은 기존 V1의 데이터 부족 계산 동작을 별도로 보존하기 위한 테스트다.
점수가 오르거나 내려가는 것은 규칙의 차이이고 정확도 향상을 의미하지 않는다.

[실제 요청](examples/search-area-compare-request.json)과
[전체 응답](examples/search-area-compare-response.json)은 TestClient POST 실행 결과다.
A의 1순위 기여점수는 V1 `30/30/14/10/8 = 92`, V2 `30/23/10/10/8 = 81`이다.

## 검증

초기 전체 테스트는 114개였고 최종 188개가 통과했다. 추가 테스트는 74개다.
수색 영역뿐 아니라 기존 match/embed/health, 매칭·갤러리 관련 테스트를 모두 실행했다.
실제 Overpass 네트워크는 테스트에 사용하지 않았다.

| 명령 | 결과 |
| --- | --- |
| uv lock --check | 통과 |
| uv sync --locked --dev | 통과 |
| uv run pytest | 188 passed |
| uv run ruff check . | 통과 |
| uv run ruff format --check . | 통과; 78 files already formatted |
| uv run python -m compileall -q app tests | 통과 |
| git diff --check | 통과 |

기존 FastAPI/Starlette TestClient의 httpx 사용 deprecation 경고 1개가 있다.
검사 실패는 없고 의존성 추가로 해소하는 범위 밖 변경은 하지 않았다.
기존 GitHub workflow는 develop/main 배포용이며 추가 테스트 검사는 없다.
배포 실행은 이번 범위에서 제외했다.

## 연동 및 제한

Backend는 기존 요청 DTO를 그대로 전달하고 `reportId`, offset 포함 `comparedAt`,
`baseline`, `improved`, `comparison` 응답 DTO를 추가하면 된다. 알고리즘 결과에는
버전·행동·반경·환경 출처·fallback·assumptions·areas가 있고, 각 영역에 nullable
scoreBreakdown이 있다. 비교 순위는 BOTH/ADDED/REMOVED와 nullable before/after,
중심 이동·점수차·reasonCode 추가/제거를 제공한다. 전체 필드·타입은 API 문서에 명시했다.

Frontend는 버전별 지도 원, “수색 우선점수”, 기여점수와 reason/assumptions를 표시한다.
null breakdown은 환경 점수 없음으로 처리하고, null 이동/점수차를 0으로 바꾸지 않는다.
동일 rank 비교를 같은 물리 영역의 이동으로 표시하지 않는다. V1 LOW_TRAFFIC은
실시간 교통 정보가 아니며 fallback에서 개선 효과를 표시하지 않는다.

요청 범위에서 미구현 항목은 없다. 운영 환경에서의 실 Overpass 실측이나 발견 정확도
평가는 하지 않았다. OSM 대표점·국소 평면 근사 및 데이터 누락의 한계가 있다.
실제 이동 경로·통행 가능성·교통·날씨·고도·목격 보정·고양이·DB·배포는 범위 밖이다.
수색 우선순위는 확률이 아니며, 실제 발견 데이터가 확보되면 추가 평가가 필요하다.

## 로컬 커밋

1. `f9f81e8ad6668adb92062af22594d8c3f0de9676` — V1 회귀 기준
2. `594800b83eca52bdf572a565bf32a1e9a782b837` — 점수 기여도 추적·집계
3. `b37264a10c2f29ca6447a954925313649b4178f5` — 거리 기반 V2
4. `27224c069c233b56818088b2ac381ec248b8bf0e` — 비교 API와 추천 이유
5. 문서 커밋 — 이 보고 및 API 계약·실제 예시 (정확한 SHA는 최종 응답/git log)
