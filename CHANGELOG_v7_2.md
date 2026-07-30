# v7.2

- 기준: 사용자가 다시 올린 연수문화공원 + 달빛공원 정상 원본
- scraper.py(연수) 및 songdo_scraper.py(달빛)는 수정하지 않음
- 새아침테니스장을 독립 saeachim_scraper.py로 추가
- 공식 SSO 주소 우선 진입, direct URL 보조 진입
- 고정 ID뿐 아니라 전체 select/버튼 텍스트를 검색하는 적응형 시설·코트 선택
- 코트별 오류 격리 및 다음 코트 계속 진행
- 짧은 단계별 timeout으로 영구 정지 방지
