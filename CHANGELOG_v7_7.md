# v7.7

- 새아침 `wait_for_function`의 Playwright 호출 형식을 현재 버전에 맞게 수정 (`arg=` 키워드).
- 달빛 10개 코트 × 후보 날짜 API를 순차 조회에서 제한 병렬 조회로 변경.
- 기본 동시 요청 수 20개, Railway 변수 `DALBIT_API_CONCURRENCY`로 4~32 사이 조정 가능.
- 연수문화 조회 및 텔레그램 알림 로직은 변경하지 않음.
