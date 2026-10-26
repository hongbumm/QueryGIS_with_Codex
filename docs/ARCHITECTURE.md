# 기존 QueryGIS를 사용하는 Codex 플러그인

## 소유권

QueryGIS가 하는 GIS 작업은 기존과 같습니다. 새 기능은 외부 작업 전달과 상태 회신입니다.

- Codex는 목표를 전달하고 결과를 확인합니다.
- 기존 QueryGIS가 선택 레이어 문맥, 자체 발급 Key, 서버 URL과 요청 payload를 정합니다.
- 기존 QueryGIS_Flask가 Key 검증, AI 공급자 자격증명, 모델, 지침, RAG와 수정 요청을 관리합니다.
- 기존 QueryGIS가 생성 코드를 QGIS에서 실행합니다.

## QGIS 연결부

`qgis_plugin/querygis_codex_connector`는 원본 QueryGIS의 사본을 포함하지 않습니다. 설치·활성화된 QueryGIS 인스턴스를 찾고 `process_query()`를 호출합니다.

요청이 실행되는 동안 `handle_response`, `handle_error`, `run_code_string`, `append_chat_message`, `_start_backend_attempt`를 메모리에서 감싸 진행과 결과를 관찰합니다. 원래 메서드는 그대로 호출하며 연결 해제 시 복원합니다. 디스크의 원본 플러그인과 서버 파일을 편집하지 않습니다. 초기 응답이 `tool_followup`이나 RAG 재요청을 시작하면 다음 응답까지 같은 작업을 유지합니다. 기존 코드의 동기 `/fix-code` 경로도 그대로 유지됩니다.

HTTP 스레드에는 QGIS 객체를 전달하지 않습니다. QTimer가 메인 스레드에서 작업함을 읽고 기존 QueryGIS를 호출합니다. 새 레이어 ID·유효성·개수와 기존 출력 메시지는 관찰 결과입니다. 결과의 의미적 정확도까지 연결부가 별도로 판정하지 않습니다.

연결 중 다른 플러그인이 같은 메서드를 바꾸거나 원본 QueryGIS 자체를 재로드한 경우에는 연결을 껐다 다시 켜야 합니다. 대상 인터페이스가 맞지 않으면 명시적으로 실패합니다.

## Codex 패키지

`plugins/querygis/plugin.json`, `mcp.json`, `skills/`, `server/`, `assets/`를 하나의 실제 플러그인으로 설치합니다. `.agents/plugins/marketplace.json`은 개인/저장소 마켓플레이스에 QueryGIS를 노출합니다.

MCP 어댑터에는 QueryGIS 서비스 Key나 AI 공급자 Key를 받는 입력이 없습니다. `launch.py`는 설치 시 준비한 로컬 Python 실행 경로를 읽어, 플러그인이 Codex 캐시에 복사되어도 SDK를 찾을 수 있게 합니다. SDK는 고정한 `mcp==2.3.0`을 사용합니다. 시스템 Python은 3.11 이상이어야 합니다.

연결 API는 인증된 `GET /health`, `POST /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel`뿐입니다. 서비스 Key 입력·모델 변경·임의 코드 실행 API는 없습니다.

## 기존 서버 계약에서 확인한 내용

`QueryGIS_Flask/app.py`의 `/chat`과 `/fix-code`는 사용자 `api_key`를 유효/폐기 목록과 비교합니다. 실제 AI 호출에는 서버의 `GOOGLE_API_KEY`를 사용합니다. OAuth 경로는 기존 구독 검사와 사용량 기록을 사용합니다. 이 연결부는 해당 분기를 구현하거나 재정의하지 않습니다.

## 공식 문서

- [플러그인 패키징과 개인 마켓플레이스](https://developers.openai.com/plugins/build/plugins)
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)
- [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)
