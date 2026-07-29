# ChaenissBot v6 beta

기존 **연수문화공원 A/B/C 감시 기능을 보존**하면서 달빛공원 감시 모듈을 분리 추가한 베타 버전입니다.

## 이번 버전에 추가된 것

- Telegram `/settings`에서 사이트별 ON/OFF
  - 연수문화공원
  - 달빛공원 β
- 달빛공원 전용 `songdo_scraper.py`
- Playwright Chromium 기반 실제 화면 렌더링
- 달빛공원 코트·날짜·시간·예약 가능 버튼 수집
- 사이트를 포함한 고유 키로 중복 알림 및 재오픈 알림 처리
- 달빛공원 분석용 마지막 HTML 및 로그인 상태 자동 저장

## 안전한 기본값

달빛공원는 기본적으로 꺼져 있습니다. 따라서 기존 연수문화공원 봇은 예전처럼 계속 동작합니다.
달빛공원 기능은 Telegram `/settings`에서 `달빛공원 β` 버튼을 눌렀을 때만 켜집니다.

## Railway 필수 Variables

- `BOT_TOKEN`
- `CHAT_ID`

## 달빛공원 선택 Variables

- `SONGDO_ENABLED=false` — 처음부터 켜려면 `true`
- `SONGDO_COURTS=6,7,8` — 비워두면 화면에서 발견한 모든 코트
- `SONGDO_AUTH_STATE` — 로그인 상태 JSON 문자열 또는 Railway Volume의 JSON 파일 경로
- `SONGDO_DEBUG_DIR=/data/songdo_debug` — 분석 파일 저장 경로

달빛공원 예약 화면이 로그인 없이 조회되면 `SONGDO_AUTH_STATE`는 필요하지 않습니다.
로그인이 필요한 경우 Playwright storage-state JSON이 필요합니다.

## 주의: 베타 상태

달빛공원는 일반 REST 페이지가 아니라 WebSocket 및 클라이언트 Query 캐시를 사용하는 사이트입니다. 이번 버전은 내부 통신 규약을 흉내 내지 않고 실제 Chromium 화면을 렌더링해 읽는 안전한 방식입니다.

다만 사이트의 날짜 선택 UI와 코트 선택 UI가 변경되거나, Railway에서 로그인 세션이 만료되면 달빛공원 조회 오류가 발생할 수 있습니다. 이때 기존 연수문화공원 코드는 손상되지 않지만, 통합 감시 루프는 오류 알림 후 자동 재시도합니다.

분석 파일:

- `songdo_debug/songdo_last.html`
- `songdo_debug/songdo_storage_state.json`

## 배포

기존 Railway 프로젝트를 바로 덮어쓰기보다 새 프로젝트에서 먼저 테스트하는 것을 권장합니다. Chromium 설치 때문에 첫 빌드는 기존 버전보다 오래 걸리고 이미지 용량도 더 큽니다.

Trigger Railway redeploy

## v6.4 Hybrid API 개선

- 잘 동작하던 v6.1.17의 예약 화면 진입 및 DOM 수집 로직을 그대로 유지합니다.
- 최초 정상 수집 때 5~14번 코트의 facilityId를 `facility_map.json`에 자동 저장합니다.
- facilityId 10개가 모두 저장된 다음 검사부터 Convex 공개 API를 우선 사용합니다.
- API가 실패하면 자동으로 기존 DOM 수집 방식으로 복귀합니다.
- 기존 텔레그램 알림, 중복 방지, 연수문화공원 수집 로직은 변경하지 않았습니다.

## v6.5 FAST RECOVERY
`facility_map.json`이 없으면 5~14번 코트 상세를 한 번씩만 열어 Convex WebSocket에서 시설 ID를 수집합니다. 완료 즉시 API 조회로 전환하며, 실패하면 기존 DOM 방식으로 자동 복구합니다.


## v6.6 FAST ALERT
- 달빛공원은 5~14번 코트만 감시합니다.
- 5~8번은 하드코트, 9~14번은 인조잔디로 알림에 표시합니다.
- 저장된 일부 facilityId도 바로 API 조회하며, 누락 코트는 ID 수집 직후 즉시 빈자리를 조회합니다.
- 전체 코트를 다시 훑지 않고 아직 확인하지 못한 코트만 DOM으로 보완합니다.
