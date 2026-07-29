# v6.1.7 STATE-AWARE ACTUAL-DOM

- 목록/상세 화면을 먼저 판별하도록 수정
- 상세 화면 진입 상태면 `aria-label="목록으로"`로 복귀
- 목록 코트명 태그를 가정하지 않고 정확한 텍스트로 카드 탐색
- `wait_for_function()` 제거, Python 폴링으로 교체
- 실제 `button[data-date-key]`와 `title="n/m 예약 가능"` 구조 사용
- 코트별 오류 격리 및 디버그 HTML/스크린샷 저장

# v6 beta 변경사항

1. 기존 연수문화공원 scraper는 유지했습니다.
2. 달빛공원 Playwright scraper를 별도 파일로 추가했습니다.
3. 사이트별 켜기/끄기 버튼을 Telegram 설정 화면에 추가했습니다.
4. 슬롯 키에 사이트 구분자를 넣어 서로 다른 사이트의 동일 날짜/시간이 충돌하지 않게 했습니다.
5. 달빛공원 기능은 기본 OFF라 기존 운영 동작에 영향을 주지 않습니다.
6. Railway Dockerfile에 Chromium 설치 단계를 추가했습니다.

## 아직 실제 환경에서 검증이 필요한 부분

- 달빛공원의 날짜 선택 DOM 구조
- 로그인 세션 만료 시점
- Railway IP에서의 사이트 접근 허용 여부
- 사이트 UI 변경 시 선택자 보정

## Railway build fix
- Python base image pinned to `python:3.12-slim-bookworm`.
- Fixes Playwright dependency installation failure caused by unavailable `ttf-unifont` packages on newer Debian images.


## v6.1.8 CLICK-PROBE
- 코트명 탐색, 카드 DOM, 카드 내부 버튼 상태를 Railway 로그로 출력
- 클릭 전/후 URL, 목록으로 버튼, 코트명, 날짜 버튼 개수 검증
- 실패 단계별 HTML/스크린샷 저장(컨테이너 내부 진단용)
- 검증되지 않은 진단 버전이며 예약 수집 성공을 보장하지 않음


## v6.1.9 RESERVATION-ENTRY
- Prime Reserve 메인에서 `예약` 메뉴를 실제 클릭하도록 진입 흐름 수정
- button뿐 아니라 link, tab, role=button, 정확한 텍스트 후보를 순차 탐색
- 후보별 태그·role·href·aria-label·가시성·활성 상태를 Railway 로그로 출력
- 일반 클릭 실패 시 force 클릭을 추가로 시도
- `domcontentloaded` 뒤 `networkidle` 및 Prime Reserve 앱 셸 렌더링 대기
- 클릭 후 반드시 5번·14번 코트 존재 여부로 예약 목록 진입 검증
- 아직 실제 Railway 환경에서 검증 전인 진단 수정본


## v6.1.10 CLICK-FALLBACK
- 예약 버튼 클릭 TimeoutError를 즉시 실패로 처리하지 않고 상세 진입 여부를 먼저 검증
- Playwright 일반 클릭에 `no_wait_after=True` 적용
- 일반 클릭 후 상세 미진입 시 DOM `click()` 대체 시도
- 클릭 후 `목록으로` 버튼과 날짜 버튼이 실제 나타날 때까지 폴링
- 검증되지 않은 진단 버전이며 실제 예약 슬롯 수집 성공을 보장하지 않음

## v6.1.12 NESTED-MODAL
- 코트 상세 화면 자체가 `data-state="open"` 오버레이인 구조를 반영했습니다.
- 날짜 조회 전 상세 오버레이는 유지하고, 그 위의 날짜/시간/안내 하위 모달만 닫습니다.
- 다음 코트 카드 클릭 전에 남아 있는 하위 모달을 정리합니다.
- 코트 예약 버튼은 DOM click을 우선 사용해 포인터 가로채기 타임아웃을 피합니다.
- 목록 복귀가 확인되지 않으면 예약 URL을 다시 접속합니다.
