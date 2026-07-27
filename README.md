# ChaenissBot

연수문화공원 테니스장 A/B/C의 공개 예약 달력을 감시합니다.

- 평일: 20:00~22:00
- 주말: 모든 시간
- 새로 생긴 빈자리만 Telegram 알림
- 사라졌다가 다시 열린 자리도 다시 알림
- 6시간마다 정상 작동 heartbeat

## Railway Variables

필수:

- `BOT_TOKEN`: BotFather에서 발급한 새 토큰
- `CHAT_ID`: 본인 Telegram Chat ID

선택:

- `CHECK_INTERVAL`: 검사 주기(초), 최소 30, 기본 60
- `HEARTBEAT_HOURS`: 정상 작동 알림 주기(시간), 기본 6
- `REQUEST_TIMEOUT`: 사이트 요청 제한시간(초), 기본 20

## Railway 설정

- Start Command: `python main.py`
- Serverless/App Sleeping: 끄기
- Restart Policy: Always

## 로컬 테스트

```bash
python -m pip install -r requirements.txt
set BOT_TOKEN=새토큰
set CHAT_ID=내ChatID
python main.py --test-telegram
python main.py --once
```
