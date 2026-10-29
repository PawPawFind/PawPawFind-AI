# 수색 영역 V2 및 비교 API 계약

`POST /search-areas`의 요청·응답 및 HEURISTIC_V1 결과는 보존한다.
추가된 `POST /search-areas/compare`는 같은 `SearchAreaRequest`로 V1과 V2를 함께 실행한다.
인증, DB 저장, Backend/Frontend 변경, 배포는 이번 구현 범위에 포함하지 않는다.
새 의존성은 없다. 런타임 스키마는 `/openapi.json`에서도 확인할 수 있다.

## V1 보존 기준

기준 커밋은 최신 develop의 `ef43a3a`이다. V1의 행동 분류, 크기·경과 시간·활동량·
이동 제한·도주 원인의 반경 배수, 300~3000m 반경, 200m 격자, 환경 선호도,
300m 이내 환경 종류의 존재에 따른 점수, 기존 reason/reasonCodes를 유지한다.
점수 임계값으로 인접 격자를 군집화하고 중복 영역을 제거한다. 독립 군집이 부족하면
기존 대표 격자 선정으로 최소 2개를 확보한다. 독립 유효 후보가 있으면 최대 3개이다.
후보의 평균 점수 반올림, 좌표 정밀도, 순위, 반경 150~500m도 유지한다.

`tests/fixtures/search_area_v1.json`은 구현 변경 전에 고정된 입력·시각·환경에서 얻은
6가지 전체 V1 wire 응답이다. 기존 API 응답과 비교 API baseline의 기존 필드를 검증한다.
기존 V1 코드의 문법 표현과 `LOW_TRAFFIC`도 호환성 때문에 유지한다.
`LOW_TRAFFIC`은 실시간 교통량 관측값이 아니므로 UI에서 교통량이 적다는 뜻으로
번역하거나 표시하면 안 된다. V2에서는 이 코드를 생성하지 않는다.

## V2 점수

`app/search_area/scoring_v2.py`에서 별도로 계산한다. 모든 환경 거리 계산은
격자 중심과 OSM Feature **대표점** 사이의 거리이다. polygon 경계나 도로망 거리가 아니다.

```text
p(d) = max(0, 1 - d/R)
R = SearchAreaHeuristicConfig.environment_influence_meters (기본 300m)
s[k] = 환경 종류 k에 속하는 Feature들의 p(d) 최댓값 (없으면 0)
```

0, 75, 150, 225, 300m에서 각각 1, 0.75, 0.5, 0.25, 0이다. 반경 초과는 0이다.
설정은 기존 `app/search_area/config.py`에 집중되어 있다. 환경 영향 반경을 바꾸면 V1의
조회 범위도 바뀌므로 기본값을 유지해야 현재의 V1 기준 결과를 보장할 수 있다.

| 항목 | V2 계산 (0~1) | 최종 최대 기여점수 |
| --- | --- | ---: |
| distance | V1과 동일한 `clamp(1 - 실종 위치 거리/예상 반경)` | 30 |
| behaviorEnvironment | `max(행동별 선호도[k] * s[k])`, 근거 없으면 0 | 30 |
| corridor | `max(통로 선호도[k] * s[k])`, 근거 없으면 0 | 20 |
| accessibility | `clamp(1 - sum(장애물 감점[k] * s[k]))` | 10 |
| eventContext | 아래 기존 행동별 상황 조건을 거리 감쇠로 연속화 | 10 |

행동별 선호도는 V1 설정 그대로다.

| 행동 | 환경별 선호도 |
| --- | --- |
| FEARFUL | 녹지 1.0, 주거 0.8, 상업 0.2 |
| CHASE_DRIVEN | 녹지 0.9, 보행로 1.0, 수변 0.7 |
| HUMAN_SEEKING | 상업 1.0, 주거 0.8, 보행로 0.7 |
| ALOOF | 녹지 0.8, 주거 0.6, 보행로 0.5 |

통로는 보행로 1.0, 녹지·수변 0.7, 일반 도로 0.3이다.
감점은 주요 도로 0.7, 철도·차단 장벽 0.8, 일반 도로 0.2이다.
동일 종류의 Feature 개수로 가산하지 않는다. 접근성 감점은 종류별로 합산하고 0에서 제한한다.
장벽 분류는 기존 OSM 태그 분류를 사용하며 실제 통과 불가능 여부를 뜻하지 않는다.

실종 상황 점수는 기본 0.5에서 다음 값을 반영하고 0~1로 제한한다.

- FEARFUL: `+0.3 * (1 - s[MAJOR_ROAD])`
- CHASE_DRIVEN: `+0.3 * s[FOOTPATH]`
- HUMAN_SEEKING: `+0.3 * max(s[COMMERCIAL], s[BUILDING_RESIDENTIAL])`
- ALOOF: `+0.2 * s[GREEN_SPACE]`
- 이동 제한이 있으면: `-0.3 * s[RAILWAY_BARRIER]`

기존 이진 조건이 영향 반경 경계에서 급격히 바뀌는 현상을 줄이려는 최소 변경이다.
FEARFUL의 주요 도로 미감지 가점은 V1의 규칙을 연속화한 것으로 교통량에 대한 근거가 아니다.
V1에서 빈 주변 환경에 부여하던 행동·환경 0.2 / 통로 0.1 기본점수는 V2에 부여하지 않는다.
존재하지만 선호하지 않는 환경과 환경 미감지 사이의 불연속을 줄이고, 환경 증거 없는
가점을 설명 근거로 사용하지 않기 위함이다. 접근성 1.0 및 상황 기본점수는 기존 규칙상
중립값으로 남아 있으므로 데이터가 적다고 점수 전체가 0이 되는 것은 아니다.

최종 점수는 기존 가중치 30/30/20/10/10을 적용한 0~100의 휴리스틱 수색 우선점수이다.
V2도 기존 공간 인덱스, 격자 생성, 군집화, 중복 제거, 대표 격자 및 후보 선정 로직을 사용한다.

## scoreBreakdown

비교 API의 양쪽 `areas[]`에만 추가된다. 기존 `/search-areas`에는 추가하지 않는다.
각 값은 정규화된 원점수가 아닌 **가중치가 적용된 최종 기여점수**인 정수다.

후보는 실제 구성 `ScoredCell`을 추적한다. 군집은 각 항목을 구성 격자 전체에 대해 산술평균한
후 가중치를 곱한다. 점수로 가중한 중심 좌표와 달리 점수 집계는 V1과 동일한 산술평균이다.
대표 격자 후보는 실제 선정된 단일 격자의 항목을 사용한다.
계산 중에는 float 정밀도를 유지하고 표시할 때만 다음을 적용한다.

1. 기존 `priorityScore = round(구성 격자 우선점수 평균)`을 그대로 유지한다.
   Python `round`의 정확한 .5 동률은 짝수 방향이다.
2. 항목별 실제 기여점수의 소수부를 버린다.
3. `priorityScore - 버린 점수 합`만큼 소수부가 큰 항목부터 1점씩 배분한다.
4. 소수부가 같으면 distance → behaviorEnvironment → corridor → accessibility → eventContext 순서다.

이 최대 잔여 방식은 합계가 `priorityScore`와 같고 각 범위(30/30/20/10/10)를 지킨다.
설명 순위는 표시용 정수 이전의 기여점수로 정한다. 작은 양수의 표시값은 0일 수 있다.
fallback에는 계산된 구성 격자가 없으므로 `scoreBreakdown: null`이다. 50/40점의
fallback 우선점수에서 임의로 환경 기여점수를 역산하지 않는다.

## 추천 이유

V1 문구는 보존한다. V2는 실제 기여점수의 크기 순으로 근거 2~3개를 선택한다.
행동·환경 및 통로의 경우 격자마다 실제 최댓값을 만든 환경 종류를 추적하고,
구성 격자에서 해당 항목 점수 합이 가장 큰 종류를 설명한다. 단순히 주변에 존재한다는
이유만으로 높은 선호도의 녹지를 근거로 넣지 않는다. 환경 종류 동점은 enum 문자열 순서다.
설명 항목 동점은 거리 → 행동·환경 → 통로 → 접근성 순서다.

| V2 reasonCode | 의미 |
| --- | --- |
| DISTANCE_FROM_LAST_SEEN | 실종 위치 거리의 실제 양수 기여 |
| BEHAVIOR_NEAR_{환경종류} | 행동·환경 적합도에 실제 기여한 대표 환경 |
| CORRIDOR_NEAR_{환경종류} | 통로 점수에 실제 기여한 대표 환경 |
| BARRIER_DISTANCE_CONSIDERED | 관측된 도로·장벽 대표점 거리의 감점을 고려 |
| LIMITED_ENVIRONMENT_EVIDENCE | 설명 가능한 근거가 2개 미만이어서 보수적 문구 추가 |

`{환경종류}`는 GREEN_SPACE, FOOTPATH, WATER, ROAD, COMMERCIAL,
BUILDING_RESIDENTIAL 중 해당 항목의 설정에서 양수 선호도를 갖는 종류다.
환경 미감지에 따른 접근성의 중립값 및 실종 상황 기본점수는 장소 근거로 사용하지 않는다.
상황 점수는 breakdown으로 제공하며, 환경 관계는 그 원인이 되는 행동·환경 및 통로 항목으로
설명한다. 실제 통과 가능 여부, 안전, 차량 통행량, 발견 확률, 실제 이동 경로를 주장하지 않는다.
모든 정상 V2 문구에 우선 수색을 위한 참고 정보임을 명시한다. fallback은 기존 안내를 재사용한다.

## 비교 API

```http
POST /search-areas/compare
Content-Type: application/json
```

요청 DTO는 기존 SearchAreaRequest다. `reportId` 양의 정수, `species: "강아지"`,
`size: "소형" | "중형" | "대형"`, `eventDate: YYYY-MM-DD`, WGS84 `latitude/longitude`가 필수다.
`eventHour`는 null 또는 0~23, `behaviorProfile`은 기존 UNKNOWN 기본값을 사용한다.
`happenPlace`, `description`도 그대로 허용한다. 필드 오류와 미래 실종 시각은 422다.

실제로 TestClient로 실행한 고정 요청과 전체 응답:

- [요청 JSON](examples/search-area-compare-request.json)
- [응답 JSON](examples/search-area-compare-response.json)

예시의 기준 시각은 `2026-10-29T12:00:00+09:00`이고, 환경은 실종 위치에서 북쪽 75m의
녹지 대표점 하나인 `FIXED_TEST_DATA`다. 실서비스 OSM 결과를 재현한다는 의미는 아니다.
아래는 같은 실행에서 얻은 1순위의 일부 필드다.

```json
{
  "baseline": {
    "algorithmVersion": "HEURISTIC_V1",
    "priorityScore": 92,
    "scoreBreakdown": {
      "distance": 30, "behaviorEnvironment": 30,
      "corridor": 14, "accessibility": 10, "eventContext": 8
    }
  },
  "improved": {
    "algorithmVersion": "HEURISTIC_V2",
    "priorityScore": 81,
    "scoreBreakdown": {
      "distance": 30, "behaviorEnvironment": 23,
      "corridor": 10, "accessibility": 10, "eventContext": 8
    }
  }
}
```

이 발췌의 priorityScore와 scoreBreakdown은 전체 응답에서는 각 `areas[]` 안에 있다.

### Backend DTO

| 경로 | 타입·의미 |
| --- | --- |
| reportId | 요청과 같은 정수 |
| comparedAt | Asia/Seoul offset 포함 ISO-8601 시각 |
| baseline / improved | 아래 AlgorithmSearchAreas |
| comparison | 아래 SearchAreaComparison |

`AlgorithmSearchAreas`는 `algorithmVersion`(HEURISTIC_V1/HEURISTIC_V2),
`behaviorType`(기존 4종), `estimatedRadiusMeters`(300~3000 정수),
`environmentSource`(문자열), `fallbackUsed`(boolean), `assumptions`(문자열 배열),
`areas`(ExplainedSearchArea 배열)이다. 중첩 reportId는 없다.

`ExplainedSearchArea`는 기존 영역의 `rank`, `center {latitude, longitude}`,
`radiusMeters`, `priorityScore`, `reasonCodes`, `reason`에 nullable `scoreBreakdown`을 더한다.
정상 결과의 영역 수는 2~3개이고 fallback은 2개다. `scoreBreakdown`의 키는 위 표의
camelCase 이름 5개다. nullable 필드도 JSON에서 누락하지 않고 명시적으로 null로 반환한다.

`SearchAreaComparison` 필드:

| 필드 | 타입·의미 |
| --- | --- |
| fallbackUsed | boolean; 어느 쪽이든 fallback이면 true |
| summary | 실제 영역 수, 동일 순위 중심 이동 최댓값, 점수 변화 범위와 해석 한계 |
| areaCountBefore / areaCountAfter | 정수 |
| rankChanges | rank 오름차순의 아래 비교 배열 |

`RankChange` 필드:

| 필드 | 타입·의미 |
| --- | --- |
| rank | 양의 정수 |
| status | BOTH / ADDED / REMOVED |
| beforeCenter / afterCenter | nullable center |
| centerShiftMeters | nullable 실수; 반환 좌표를 기존 geo 유틸로 비교하고 소수 3자리 반올림 |
| beforeRadiusMeters / afterRadiusMeters | nullable 정수 |
| beforePriorityScore / afterPriorityScore | nullable 정수 |
| scoreDelta | nullable 정수; after - before |
| addedReasonCodes / removedReasonCodes | 순서를 보존한 문자열 배열 차집합 |

한쪽 순위만 있으면 그쪽의 before/after 필드만 채우고 이동 거리와 scoreDelta는 null이다.
동일 순위끼리의 비교는 **동일한 물리적 영역을 추적하는 것이 아니다**.
reasonCode의 변화는 V2 설명 체계가 달라진 데서도 발생하며 환경 변화의 증거가 아니다.

### 공정한 비교 및 fallback

한 요청에서 현재 시각을 한 번 구한다. 같은 신고, 크기, 위치, 실종 시간, 프로필,
행동 유형, 예상 반경을 준비한다. 환경 제공자를 한 번 호출하고 같은 불변 환경 데이터와
같은 격자 객체들을 V1/V2에 전달한다. 각 점수 계산 중에는 시각이나 외부 API를 조회하지 않는다.
따라서 `comparedAt`은 비교 전체의 기준 시각이며 두 알고리즘 사이 시간 차이는 없다.

Overpass timeout, HTTP 오류, 파싱 오류, 빈 데이터는 기존 provider의 오류로 처리한다.
비교 전체를 실패시키지 않고 기존 fallback 영역을 양쪽에 재사용한다. 양쪽의
`fallbackUsed: true`, `environmentSource: "UNAVAILABLE"`, `scoreBreakdown: null`을 표시한다.
assumptions와 summary에 환경 비교의 한계를 알리고 V2 개선 효과를 주장하지 않는다.
환경 조회는 성공했지만 유효 후보가 부족한 버전에도 기존 fallback 정책을 적용한다.
기존 `/search-areas`의 fallback 응답은 변경하지 않는다.

### Frontend 표시 정책

- baseline과 improved를 버전별로 구분하고 중심 좌표/미터 반경으로 지도 원을 그린다.
- 점수는 “수색 우선점수”로 표시한다. %나 발견 확률, 정확도 개선율로 표시하지 않는다.
- breakdown이 null이면 차트·기여점수를 숨기고 환경 정보 부족 안내를 표시한다.
- 기여점수 차트는 최대 30/30/20/10/10, 합계는 priorityScore다.
- reasonCodes는 식별용이고 사용자 문구는 reason과 assumptions를 우선 사용한다.
- 비교는 같은 rank의 위치·반경·점수 변화다. 같은 개체 이동 경로나 같은 장소의 순위 변화로 해석하지 않는다.
- 누락된 한쪽 값과 이동 거리 null을 0으로 치환하지 않는다. ADDED/REMOVED로 구분한다.
- fallback 비교에서는 V2 개선 효과를 보여 주지 않는다. V1 LOW_TRAFFIC에 교통량 의미를 부여하지 않는다.

## 검증과 한계

외부 Overpass 호출 없이 StaticEnvironmentProvider 또는 httpx.MockTransport를 사용한다.
고정 golden 6개, 0/75/150/225/300/초과 거리, 행동 4종, 통로/장벽 감쇠,
복수·중복 환경, 군집/대표 격자 기여도, 정수 동률, API 오류, 공유 입력/단일 시계/단일 호출,
순위 개수 불일치와 fallback, 근거 코드·문구를 검증한다. V2 점수가 V1보다 항상 높다는 검증은 없다.
기존 match/embed/health도 전체 테스트에 포함한다.

추천 결과는 발견 확률이 아닌 휴리스틱 기반 수색 우선순위다. 새 ML 모델을 학습하지 않았다.
환경은 OSM Feature 대표점 기반으로 실제 면적 경계·가까운 출입구·도로 연결성을 반영하지 않는다.
OSM의 누락, 갱신 시차, 검색 반경 밖 요소 및 대표점 위치 때문에 실제 환경과 차이가 날 수 있다.
실제 이동 경로, 도로망 최단경로, 통행 가능성, 실시간 교통, 날씨, 고도, 목격 보정은 계산하지 않는다.
국소 평면 거리 근사는 최대 3km 범위 용도이며 극지방/장거리에는 적합하지 않다.
고양이 전용 추천, 저장, 배포는 구현하지 않는다.
V1/V2 점수 차이만으로 정확도 향상을 주장할 수 없으며, 실제 발견 데이터가 확보되면 추가 평가가 필요하다.
