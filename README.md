# ChaenissBot v8.0

연수문화공원·달빛공원·새아침테니스장을 독립 모듈로 감시하고, 한 Telegram 봇에서 사용자마다 다른 사이트·코트·시간 알림을 제공하는 버전입니다.

## Railway Variables
필수: `BOT_TOKEN`
권장: `ADMIN_CHAT_ID` (기존 `CHAT_ID`도 자동 호환), `DATA_DIR=/data`, `CHECK_INTERVAL=30`
새아침 URL을 별도 등록했다면 `https://reserve.insiseol.or.kr/rent/rentalSchedule?up_id=07` 이어야 합니다.

## 명령어
`/start`, `/settings`, `/status`, `/health`, `/logs`, `/test`

## 구조
- `scrapers/yeonsu`: 연수문화공원만 담당
- `scrapers/dalbit`: 달빛공원만 담당
- `scrapers/saeachim`: 새아침테니스장만 담당
- `core`: Telegram, 저장, 필터링, 사이트 등록부
- `main.py`: 세 모듈 실행 및 사용자별 알림 분배

## 다중 사용자
친구가 같은 봇을 열어 `/start`를 누르면 독립 설정이 자동 생성됩니다. 친구가 연수문화공원만 켜 두면 연수문화공원 알림만 받습니다.

## 운영 원칙
Railway는 `main` 브랜치 하나만 운영하세요. 기능 브랜치는 운영용 BOT_TOKEN을 사용하지 마세요. 동일 토큰으로 두 인스턴스를 실행하면 getUpdates 충돌이나 중복 알림이 생길 수 있습니다.
