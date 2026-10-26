# QueryGIS for Codex

**기존 QueryGIS를 Codex의 플러그인으로 사용합니다.** QueryGIS의 GIS 기능이나 AI 처리 방식을 새로 만들지 않습니다.

```text
사용자 → Codex의 QueryGIS 플러그인 → QGIS 연결부 → 기존 QueryGIS
                                               ↕
                                    기존 QueryGIS_Flask 서버
                                               ↕
                                    기존 QueryGIS가 QGIS 실행
```

입력하는 API Key는 **QueryGIS에서 자체 발급한 서비스 인증 Key**입니다. 기존 QueryGIS가 기존 서버에 보내며, 서버가 유효성을 확인하고 서버에 보관된 AI 공급자 Key로 요청을 처리합니다. Codex 연결 때문에 사용자에게 OpenAI/Gemini Key를 추가로 요구하지 않습니다.

## 구성

| 구성 | 역할 |
| --- | --- |
| Codex 플러그인 `QueryGIS` | 자연어 작업 접수, 진행·결과 조회, 취소 요청 |
| QGIS의 `QueryGIS Codex Connector` | 설치된 기존 QueryGIS에 작업을 전달하고 결과 회신 |
| 기존 QueryGIS | 현재 패널·Key·선택 레이어 문맥·요청 생성·QGIS 실행 사용 |
| 기존 QueryGIS_Flask | 기존 인증·구독·AI 요청·RAG·코드 수정·로그 처리 |

서버 주소와 모델은 기존 QueryGIS/서버 설정을 따릅니다. 이 저장소에는 AI 공급자 직접 호출, 분석 알고리즘, 별도 코드 생성기가 없습니다. 기존 QueryGIS와 QueryGIS_Flask 저장소를 수정하거나 서버를 배포할 필요가 없습니다.

## 설치

필요한 환경: Codex 데스크톱 또는 CLI, Python 3.11 이상, 기존 QueryGIS가 설치된 QGIS 3.x. 연결부는 QueryGIS 1.x의 `process_query`/`handle_response`/`run_code_string` 인터페이스를 기준으로 합니다.

1. 이 저장소 폴더의 PowerShell에서 실행합니다.

   ```powershell
   .\scripts\setup.ps1
   ```

   MCP 실행 환경을 준비하고 개인 마켓플레이스 `querygis-local`에 **QueryGIS** 플러그인을 등록·설치합니다. 기존 0.1 버전에서 만든 동일 저장소의 단독 MCP 연결은 설치 성공 후 정리합니다. Windows의 기존 QGIS 기본 프로필을 찾으면 연결부도 설치·활성화합니다. 이전 `QueryGIS with Codex 0.1` 실험본은 해당 메타데이터가 일치할 때만 비활성화하며 파일은 보존합니다. 원본 QueryGIS와 서버 설정은 유지합니다. 실행 정책이 막히면 `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`로 이 스크립트만 실행하세요.

2. 연결부가 자동 설치되지 않았다면 QGIS의 **플러그인 → 플러그인 관리 및 설치 → ZIP 파일에서 설치**에서 `dist/querygis_codex_connector-0.2.0.zip`을 설치합니다. QGIS가 켜진 상태에서 설치했다면 재시작 후 연결부를 활성화하세요. **원래 QueryGIS도 설치·활성화된 상태여야 합니다.**
3. 기존 QueryGIS 패널에서 평소 사용하던 **QueryGIS 발급 Key 또는 로그인**을 준비합니다. Key 저장 방식도 기존 QueryGIS 동작을 따릅니다.
4. QGIS 툴바/QueryGIS 메뉴에서 **QueryGIS ↔ Codex 연결**을 켭니다. Key 입력 전에도 연결 상태 확인은 가능하며, 실제 요청 접수 시 인증 준비 여부를 확인합니다.
5. Codex에서 새 채팅을 시작합니다. 플러그인 목록에서 `QueryGIS · 개인 플러그인` 소스의 **QueryGIS**를 확인할 수 있습니다. 목록이 갱신되지 않으면 Codex 앱을 다시 시작하세요.

   ```text
   QueryGIS 연결을 확인해줘.
   QueryGIS에 선택한 학교 레이어 주변 500m 버퍼 생성을 요청하고 결과를 확인해줘.
   ```

Codex는 기존 QueryGIS의 **Ask**(`mode=ask`) 또는 **Ask and Run**(`mode=run`)을 요청합니다. 별도 공급자 선택 화면이나 새로운 분석 모드를 추가하지 않습니다.

개인 플러그인 설치가 현재 목표입니다. 공개 플러그인 디렉터리 출시는 이 작업에 포함되지 않습니다.

## 연결과 작업

Codex 도구는 `get_connection_status`, `submit_task`, `get_task_status`, `get_task_result`, `cancel_task` 다섯 개입니다. 작업 입력은 `instruction`, `request_id`, `mode`만 받습니다. 코드, 서비스 Key, 공급자 Key, 모델, 서버 주소를 받는 도구는 없습니다.

같은 `request_id`는 같은 작업을 반환하므로 전달 여부가 불명확할 때 동일 ID로 재시도하세요. 새 요청을 자동으로 다시 보내지 않습니다. 기존 QueryGIS의 정보 추가 요청(`tool_followup`), RAG 재시도, `/fix-code` 처리는 원래 메서드가 계속 담당합니다.

상태는 `queued → planning → running → succeeded/failed/cancelled`입니다. Ask는 실행 없이 성공할 수 있으므로 결과의 `executed` 값도 확인하세요. 기존 서버가 HTTP 200으로 반환하는 무효·폐기 Key 및 구독 오류도 실패로 전달합니다.

연결부는 QGIS 메인 스레드에서 기존 QueryGIS를 호출합니다. HTTP 스레드는 작업함만 사용합니다. 다른 QueryGIS 요청이 처리 중이면 대기하고, Codex 작업 중에는 기존 패널의 입력과 실행 버튼을 잠시 잠가 요청이 섞이지 않게 합니다. 작성 중이던 입력과 Ask/Run 선택은 보존합니다.

취소는 대기 작업과 아직 실행되지 않은 서버 응답을 중지합니다. 이미 실행 중인 QGIS 코드는 강제 종료하지 않으며, 완료 후 취소 상태와 관찰된 결과를 반환할 수 있습니다. 파일 쓰기나 레이어 변경의 롤백은 기존 QueryGIS 동작을 따릅니다.

## 로컬 파일

- `%LOCALAPPDATA%/QueryGIS_with_Codex/runtime.json`: 설치 시 준비한 Python 실행 경로. Key는 없습니다.
- `%LOCALAPPDATA%/QueryGIS_with_Codex/connection.json`: QGIS 연결 포트와 임시 로컬 인증 토큰. QueryGIS 서비스 Key는 없습니다.
- Windows 외 기본 위치: `~/.local/share/QueryGIS_with_Codex/`.

QGIS와 Codex는 같은 PC·같은 사용자 계정에서 실행합니다. 연결 서버는 `127.0.0.1`만 사용하며 브라우저 Origin 요청을 거절합니다. 로컬 토큰은 QueryGIS 서비스 Key와 별개입니다. `QUERYGIS_CONNECTION_FILE`로 연결 파일 위치를, `QUERYGIS_MCP_PYTHON`으로 MCP 인터프리터를 명시할 수도 있습니다.

## 개발·검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\build_plugin.py
```

빌드 결과는 QGIS 연결부 ZIP과 Codex 플러그인 ZIP 두 개입니다. 실제 Codex CLI의 플러그인 설치, MCP stdio, 독립 캐시 폴더에서의 실행, 요청 중복 방지, 인증 오류, 취소와 기존 QueryGIS 메서드 위임을 검증합니다. 일반 Qt 테스트의 QGIS 객체와 기존 QueryGIS는 모형이며 실제 공간 연산 검증을 대신하지 않습니다. 실사용 서비스 Key나 유료 AI 요청은 자동 테스트에 사용하지 않습니다.

구현 범위는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 기존 코드·자산 출처는 [UPSTREAM.md](UPSTREAM.md)를 확인하세요.

원본 QueryGIS 체크아웃이 있으면 `QUERYGIS_LEGACY_PLUGIN`을 해당 폴더로 지정해 추가 테스트 두 개를 실행할 수 있습니다. 원본 Python 코드의 `/chat`·`/fix-code` 경로를 테스트 서버로 검증하며 원본 파일과 실제 서버는 변경하지 않습니다. QGIS 객체는 여전히 모형이므로 실기 공간 분석은 별도 확인이 필요합니다.
