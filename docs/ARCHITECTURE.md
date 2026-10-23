# 역할과 실행 경계

## QueryGIS

`qgis_plugin/querygis_with_codex/plugin.py`는 원본 QueryGIS를 확장합니다. 원본 UI·레이어 표시·문맥 수집 helper를 재사용하고 새 작업 흐름을 연결합니다. 원본 `query_gis.py`의 백엔드 전용 `process_query`와 실행 재시도 경로는 새 작업에서는 사용하지 않습니다.

- QTimer가 메인 스레드에서 작업함을 확인합니다.
- 메인 스레드에서 레이어 ID를 확인하고 QGIS 객체를 JSON 데이터로 복사합니다.
- AI 요청만 별도 Python 작업 스레드에서 수행합니다. 이 스레드는 QGIS 객체를 보유하지 않습니다.
- Qt 신호로 응답을 메인 스레드에 전달합니다.
- 검토 정책을 적용한 뒤 메인 스레드에서 코드를 실행하고 새 레이어 유효성을 확인합니다.
- 실패 시 수정안 생성은 한 번만 수행하고 재실행 전 검토를 받습니다.

`bridge.py`는 인증된 루프백 HTTP 서버입니다. HTTP 스레드는 TaskStore와 복사된 상태만 읽고 쓰며 QGIS나 Qt 화면을 호출하지 않습니다.

`tasks.py`는 스레드 안전한 상태 전이와 idempotency를 제공합니다. 상태와 결과는 메모리에 있으며 QGIS 재시작 후 복구하지 않습니다. 중복 제거를 유지하기 위해 완료 작업을 자동 제거하지 않고 세션당 100건으로 제한합니다.

## Codex

`codex_mcp/server.py`는 공식 Python MCP SDK의 stdio 서버입니다. 로컬 연결 파일을 읽고 QueryGIS 작업 API를 호출합니다. MCP 서버는 QGIS를 import하지 않으며 AI 공급자를 호출하거나 API Key를 받지 않습니다.

| 도구 | 동작 |
| --- | --- |
| get_connection_status | QueryGIS가 미리 복사한 레이어 ID·이름·CRS와 공급자 설정 여부 조회 |
| submit_task | 자연어 instruction, request_id, 선택 layer_ids, ask/run 접수 |
| get_task_status | 작업 상태 조회 |
| get_task_result | 작업 상태 및 결과 레이어·출력·오류 조회 |
| cancel_task | 협력적 취소 요청 |

공개 HTTP 경로는 인증이 필요한 `GET /health`, `POST /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel`뿐입니다. 코드 실행·API Key 변경·원격 승인 API는 제공하지 않습니다. 승인과 API Key 입력은 QGIS 패널에서만 가능합니다.

이 경계는 이 플러그인이 제공하는 도구에 적용됩니다. Codex가 별도 파일/셸 도구로 QGIS에 접근할 수 있는 권한까지 이 플러그인이 OS 수준에서 제거하지는 않습니다. 제공된 스킬과 도구 instructions는 모든 QGIS 작업을 QueryGIS로 전달하도록 지시합니다.

## 참고한 공식 문서

- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)
- [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Gemini generateContent](https://ai.google.dev/api/generate-content)
- [QGIS 메인 스레드 및 작업 지침](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/tasks.html)
