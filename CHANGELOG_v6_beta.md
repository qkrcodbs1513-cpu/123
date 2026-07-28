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
