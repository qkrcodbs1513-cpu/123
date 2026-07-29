# v6.5 FAST RECOVERY

- 달빛공원 facilityId를 Vue/DOM이 아니라 실제 Convex WebSocket 송신 프레임에서 수집합니다.
- 최초 실행은 5~17번 코트 상세만 빠르게 열어 `facility_map.json`을 생성합니다.
- 13개 ID가 모이면 같은 실행에서 바로 Convex API 조회로 전환합니다.
- ID 수집/API 실패 시 기존 v6.1.17 DOM 수집으로 자동 복구하여 알림이 중단되지 않도록 했습니다.
