# ChaenissBot v3

연수문화공원 테니스장 A/B/C의 실제 `예약하기` 링크를 감시합니다.

- 평일: 20:00~22:00만 알림
- 토·일: 모든 시간 알림
- 기본 30초마다 검사
- 같은 빈자리는 한 번만 알림
- 닫혔다 다시 열린 자리는 다시 알림
- 6시간마다 Telegram 생존 확인
- 사이트 조회 오류가 5분 이상 지속되면 Telegram 알림
- 오류가 복구되면 정상 복구 알림
- 로그에 검사 시간·코트별 결과·신규/사라진 자리 표시

## Railway Variables

- `BOT_TOKEN`: 새 Telegram Bot Token
- `CHAT_ID`: Telegram Chat ID
- `CHECK_INTERVAL`: `30`
- `HEARTBEAT_HOURS`: `6`
- `ERROR_ALERT_MINUTES`: `5`
- `REQUEST_TIMEOUT`: `20`
- `TZ`: `Asia/Seoul`

Start Command는 `python main.py`입니다.
