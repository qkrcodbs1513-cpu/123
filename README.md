# ChaenissBot v5

연수문화공원 테니스장 A/B/C 빈자리를 확인하고 Telegram으로 알려주는 봇입니다.

## 포함 기능

- 30초 간격 감시
- 신규 빈자리 1회 알림
- 빈자리가 닫혔다 다시 열리면 재알림
- 오류 지속 및 정상 복구 알림
- 감시 루프/명령 루프 자동 재시작
- 상태 파일 원자적 저장 및 백업 복구
- A/B/C 코트 선택
- 평일/주말 시간 설정
- Telegram `/settings`, `/status`, `/stats`, `/check`, `/help`
- Telegram 버튼으로 설정 변경
- 검사/알림/오류/복구 통계
- Railway 재시작 정책 파일 포함

## Railway Variables

필수:

- `BOT_TOKEN`
- `CHAT_ID`

선택:

- `CHECK_INTERVAL=30`
- `HEARTBEAT_HOURS=6`
- `ERROR_ALERT_MINUTES=5`
- `REQUEST_TIMEOUT=20`
- `TELEGRAM_POLL_TIMEOUT=25`

## 주의

Railway의 기본 디스크는 재배포 때 초기화될 수 있습니다. 완전한 영구 상태 보존이 필요하면 Railway Volume을 연결하고 `DATA_DIR`를 그 경로로 지정하세요.

예:
- Volume mount path: `/data`
- Variable: `DATA_DIR=/data`
