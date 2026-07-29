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

## v6.3 달빛공원 API 전용 방식
첫 실행 시 달빛공원 5~17번 코트의 카드만 한 번씩 확인하여 `facility_map.json`을 만듭니다. 이 과정이 끝난 뒤부터는 코트·달력·날짜를 순회하지 않고 Convex API로만 빈자리를 확인합니다.

Railway Volume을 사용하는 경우 `DATA_DIR`을 Volume 경로로 지정하면 재배포 후에도 `facility_map.json`이 유지됩니다. 파일이 없거나 일부 코트가 누락되면 누락된 코트만 자동으로 다시 수집합니다.
