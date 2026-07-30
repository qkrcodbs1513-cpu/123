# v7.6

- 사용자가 브라우저에서 확인한 실제 공개 조회 주소 `https://res.insiseol.or.kr/rent/rentalSchedule?up_id=07`로 직접 진입
- 잘못된 `reserve.insiseol.or.kr` 메인 메뉴 탐색 로직 제거
- `/share/js/devtools-detector.js` 로딩 차단 및 빈 `devtoolsDetector` 객체 선주입
- 탐지 경고창이 발생해도 자동으로 닫도록 처리
- 새아침 브라우저는 주기당 한 번만 실행
- 연수문화공원·달빛공원 스크래퍼는 변경하지 않음
