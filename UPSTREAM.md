# 기존 QueryGIS와의 관계

- 원본: https://github.com/hongbumm/QueryGIS
- 참고한 인터페이스 기준 커밋: `9beec9c173c18a14f398cfd226166c50901a13de`
- 원본 제작자: 3DLabs, Juseong Lee
- 서버 계약은 로컬 `QueryGIS_Flask/app.py`의 `/chat`, `/fix-code`, Key 인증 및 추가 정보 요청 처리에서 확인했습니다.
- 0.2 버전은 설치된 기존 QueryGIS를 호출합니다. 원본 `query_gis.py`, UI, AI 지침이나 공급자 호출 코드를 제품 패키지에 복사하지 않습니다.
- 아이콘과 로고는 원본 QueryGIS 자산을 재사용했습니다.
- 기존 QueryGIS와 QueryGIS_Flask 저장소 및 운영 서버는 수정하지 않습니다. 이 저장소의 로컬 연결부만 개발·설치합니다.
