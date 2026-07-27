# ChaenissBot v2

연수문화공원 테니스장 A/B/C의 실제 `예약하기` 링크를 감시합니다.

- 평일: 20:00~22:00만 알림
- 토·일: 모든 시간 알림
- 30초마다 검사
- 같은 빈자리는 한 번만 알림
- 닫혔다 다시 열린 자리는 다시 알림
- 매일 오전 9시(KST) 생존 확인
- 반복 오류 시 Telegram 알림

## Railway Variables

- `BOT_TOKEN`: 새 Telegram Bot Token
- `CHAT_ID`: Telegram Chat ID
- `CHECK_INTERVAL`: `30`
- `HEARTBEAT_HOUR`: `9`
- `REQUEST_TIMEOUT`: `20`
- `TZ`: `Asia/Seoul`

Start Command는 `python main.py`입니다.
