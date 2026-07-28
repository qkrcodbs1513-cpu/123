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
