# ChaenissBot v4

연수문화공원 테니스장 A/B/C의 실제 `예약하기` 링크를 감시합니다.

- 평일: 20:00~22:00만 알림
- 토·일: 모든 시간 알림
- 30초마다 확인
- 신규 빈자리 1건당 Telegram 카드 + 예약 버튼
- 사라진 뒤 다시 열린 빈자리 재알림
- 빠르게 재등장한 빈자리는 긴급 표시
- 6시간마다 정상 작동 알림
- 오늘 신규 알림 건수와 연속 가동시간 표시
- 사이트 오류가 5분 이상 지속되면 알림
- 정상 복구 시 알림
- Railway 로그를 A/B/C 조건 일치 수 중심으로 간단히 표시

## Railway Variables

- `BOT_TOKEN`: 새 Telegram Bot Token
- `CHAT_ID`: Telegram Chat ID
- `CHECK_INTERVAL`: `30`
- `HEARTBEAT_HOURS`: `6`
- `ERROR_ALERT_MINUTES`: `5`
- `REQUEST_TIMEOUT`: `20`
- `REOPEN_URGENT_SECONDS`: `90`
- `TZ`: `Asia/Seoul`

Start Command는 `python main.py`입니다.
