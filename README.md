# QueryGIS_with_Codex

QueryGIS의 기본 채팅·레이어 문맥·PyQGIS 실행 기능에 API Key 입력과 Codex 연결을 더한 **비공개 실험 프로젝트**입니다.

**QGIS 작업의 주체는 QueryGIS입니다.** Codex는 자연어 작업을 접수하고 진행 상황과 결과를 조회합니다. GIS 분석 방법 결정, AI 요청, 코드 생성, QGIS 실행, 오류 수정안 생성은 QueryGIS가 담당합니다.

```text
Codex ↔ 로컬 MCP 어댑터 ↔ QueryGIS 작업함 ↔ QGIS
                              ↓
                    선택한 AI 공급자의 API
```

## 포함된 기능

- 기존 QueryGIS의 채팅 패널, 선택 레이어 표시, 벡터·래스터 문맥 수집을 재사용합니다.
- OpenAI / Gemini API Key 입력 및 모델 선택. 기존 QueryGIS `/chat` 서버 연결도 선택할 수 있습니다.
- 기존 서버가 없어도 OpenAI 또는 Gemini에 직접 요청할 수 있습니다.
- QueryGIS가 생성한 PyQGIS 코드를 QGIS 메인 스레드에서 실행하고 새 레이어의 유효성·개수를 반환합니다.
- 실패 시 QueryGIS가 수정안을 한 번 생성합니다. 일부 작업이 이미 적용됐을 수 있어 수정안은 패널에서 검토 후 실행합니다.
- Codex는 `get_connection_status`, `submit_task`, `get_task_status`, `get_task_result`, `cancel_task`만 사용합니다.
- 같은 `request_id`의 재요청은 동일 작업을 반환합니다. 코드·API Key·명령 실행 필드는 받지 않습니다.

## 빠른 시작 (Windows)

필요한 환경: QGIS **3.28 이상 3.x**, Codex 데스크톱/CLI, 별도 Python **3.11 이상**, 사용할 AI 공급자의 API Key. QGIS Python의 `requests` 패키지가 필요합니다. 이 플러그인은 QGIS 내부에서 패키지를 자동 설치하거나 QGIS를 강제 재시작하지 않습니다.

1. 이 저장소를 로컬에 준비한 뒤 PowerShell에서 실행합니다.

   ```powershell
   .\scripts\setup.ps1
   ```

   프로젝트 전용 `.venv`에 MCP를 설치하고 Codex에 `querygis_with_codex` 연결을 등록하며 플러그인 ZIP을 생성합니다. `python`이 다른 실행 파일이면 `-PythonCommand 'C:\경로\python.exe'`를 지정하세요. 실행 정책으로 스크립트가 막히면 `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`로 이 스크립트만 실행할 수 있습니다.

2. QGIS → **플러그인 → 플러그인 관리 및 설치 → ZIP 파일에서 설치**에서 `dist/querygis_with_codex-0.1.0.zip`을 설치합니다.
3. **QueryGIS with Codex** 패널을 열고 공급자·모델·API Key를 입력합니다. OpenAI 기본 모델은 `gpt-5.5`이며 계정에 접근 가능한 모델명으로 바꿀 수 있습니다. Gemini와 기존 서버는 사용할 모델명을 직접 입력합니다.
4. **연결 시작**을 누릅니다. API Key는 저장소나 Codex 설정에 기록되지 않으며 현재 QGIS 세션 메모리에서만 사용됩니다.
5. Codex에서 **새 채팅**을 시작합니다. 도구가 나타나지 않으면 앱을 다시 시작하세요.

   ```text
   QueryGIS 연결과 레이어 목록을 확인해줘.
   그다음 학교 레이어 주변 500m 버퍼를 QueryGIS에 요청하고 결과를 확인해줘.
   QGIS 작업은 반드시 QueryGIS 도구를 통해 처리해줘.
   ```

6. 기본값은 **QGIS 패널에서 생성 코드를 검토한 뒤 실행**입니다. `검토한 작업 실행`을 누르세요. 반복 실험에서 직접 실행하려면 `Codex 요청의 생성 코드를 자동 실행`을 켭니다. 패널 자체의 Ask and Run은 기존처럼 동작합니다.

QGIS 플러그인과 Codex는 같은 PC·같은 사용자 계정에서 실행해야 합니다. macOS/Linux용 MCP 등록도 `python scripts/configure_codex.py`로 가능하지만 별도 실기 검증은 하지 않았습니다.

## API Key와 연결 정보

- QueryGIS 공급자 API Key와 Codex 로그인은 별개입니다. Codex 구독으로 외부 공급자 API 비용을 대체하지 않습니다.
- API Key는 QueryGIS의 공급자 요청 헤더(기존 서버는 `/chat` 본문)에만 전달됩니다. Codex에는 전달하지 않습니다.
- 분석에 필요한 레이어 ID·이름·좌표계·필드·최대 3개 속성 샘플이 선택한 AI 공급자에 전송됩니다. 데이터 원본 연결 문자열과 프로젝트 경로는 새 계획 요청 문맥에서 제외합니다.
- 로컬 연결은 `127.0.0.1`의 임의 포트를 사용하고 매번 생성한 토큰으로 인증합니다. 브라우저 Origin이 있는 요청은 거절합니다.
- 연결 파일 기본 경로: Windows `%LOCALAPPDATA%/QueryGIS_with_Codex/connection.json`, 그 외 `~/.local/share/QueryGIS_with_Codex/connection.json`. API Key는 이 파일에 없습니다. 경로는 양쪽의 `QUERYGIS_CONNECTION_FILE` 환경변수로 바꿀 수 있습니다.
- 생성된 Python은 QGIS 사용자 권한으로 실행됩니다. 이 실험 버전은 코드를 격리하는 보안 샌드박스가 아닙니다. 기본 검토 기능을 두었으며 원본 데이터를 복사한 실험 프로젝트로 시작하세요.

## 작업 상태와 제한

`queued → planning → awaiting_approval → running → succeeded/failed/cancelled`

자동 실행 시 `awaiting_approval`을 건너뜁니다. Ask는 계획 답변으로 완료됩니다. 한 번에 한 작업을 실행하고, 연결이 끊겨도 새 요청 ID로 재접수하지 말고 기존 ID부터 조회하세요. 한 플러그인 세션에 최대 100개 작업을 보관합니다.

대기·계획·검토 작업은 즉시 취소됩니다. 실행 중 취소는 Processing feedback을 통한 협력 방식이며 일반 Python 코드를 강제 중단하지 않습니다. 기존 데이터 수정이나 파일 쓰기를 완전히 되돌리는 트랜잭션은 제공하지 않습니다. 오류가 났거나 취소됐다면 이미 생성된 결과를 먼저 확인하세요. 긴 작업 중에는 QGIS 화면 반응이 늦어질 수 있습니다.

## 개발·검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\build_plugin.py
```

자동 검증은 실제 HTTP 연결, 실제 MCP stdio 프로세스, 요청 중복 방지, 인증, 취소, 공급자 요청 형식, Qt 화면·메인 스레드 실행 흐름을 포함합니다. **Qt 테스트의 QGIS 객체는 모형**이므로 실제 GIS 연산 정확도나 실제 QGIS 설치 호환성 검증을 대신하지 않습니다. 실제 공급자 API를 호출하는 유료 테스트는 자동 실행하지 않습니다.

QGIS 실기 확인 순서:

1. `EPSG:5179`의 테스트 점 레이어를 만들고 패널에서 조회합니다.
2. 패널 Ask로 레이어와 좌표계를 설명하도록 합니다.
3. Ask and Run으로 500m 버퍼를 생성하고 결과 레이어·거리 단위를 확인합니다.
4. Codex에서 동일 작업을 접수하고 검토·실행·완료 결과를 확인합니다.
5. 잘못된 레이어 ID, 잘못된 Key, 취소, 연결 종료를 확인합니다.

API 호출 없이 실행기만 확인하려면 설치된 QGIS의 Python 콘솔에서 `scripts/qgis_smoke.py`를 실행할 수 있습니다. 자체 메모리 레이어로 500m 버퍼를 만들고 CRS·개수·면적을 검증한 뒤 해당 테스트 레이어만 정리합니다.

구조와 재사용 출처는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [UPSTREAM.md](UPSTREAM.md)에 정리했습니다.
