# ChaenissBot v7.1 — 새아침테니스장 추가

기준 파일: 사용자가 제공한 `연수문화 달빛 완성 메인.zip`

## 변경 사항
- 기존 연수문화공원 및 달빛공원 코드는 유지
- 새아침테니스장 1~4코트 감시 추가
- 새아침 사이트별 ON/OFF, 코트, 평일/주말 시간 설정 추가
- 새아침 실제 대관 페이지 주소 사용: `https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07`
- 새아침 사이트 오류 시 연수문화공원과 달빛공원 감시·알림은 계속 실행
- 오류가 난 사이트의 기존 빈자리 기준값은 보존하여 복구 후 대량 재알림 방지

## Railway
기존 Variables를 그대로 사용합니다. 별도 설정은 필수가 아닙니다.
선택 환경변수:
- `SAEACHIM_ENABLED=true`
- `SAEACHIM_URL=https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07`
