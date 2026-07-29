# v7.1.2 — 달빛·새아침 두 곳만 수정

- 달빛공원: 월별 Convex API를 2회 재시도하고, 오류가 있으면서 결과가 0개면 성공으로 오판하지 않고 기존 DOM 방식으로 복구합니다.
- 새아침테니스장: Railway에 잘못된 SAEACHIM_URL이 남아 있어도 실제 대관 페이지(`res.insiseol.or.kr/rent/rentalSchedule?up_id=07`)로 강제 진입합니다.
- 연수문화공원, 텔레그램 설정, 알림 판정 로직은 변경하지 않았습니다.
