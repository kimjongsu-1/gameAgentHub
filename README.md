# GameAgentHub

MCP 기반 로컬 AI 에이전트 자동화 허브입니다. 자연어 작업 지시를 로컬 문서 분석, 작업 분기, 이미지 에셋 생성 요청, 후처리, QA 검증, 승인 게이트, Unity 전달 준비까지 이어지는 반복 가능한 파이프라인으로 구성했습니다.

이 저장소의 핵심은 특정 게임 콘텐츠보다, 생성형 AI 결과물을 실제 프로젝트 리소스로 만들기 위한 로컬 자동화 구조입니다.

## 핵심 구현

- FastAPI 기반 로컬 컨트롤 허브
- MCP 서버를 통한 외부 에이전트/작업 채팅 연동
- 작업 지시, 상태, 승인, 전달 결과를 추적하는 API
- PostgreSQL 및 SQLite 실행 모드 지원
- Docker Compose 기반 실행 환경
- 로컬 파일 시스템 기반 산출물 관리
- Python/Pillow 기반 이미지 후처리 및 스프라이트 QA
- JSON manifest 기반 산출물 추적
- 사용자 승인 전 downstream 전달을 차단하는 게이트 구조

## 대표 테스트 산출물

포트폴리오에서 빠르게 확인할 수 있도록 대표 에셋, GIF, 검증 리포트만 모은 축약본을 별도 폴더에 정리했습니다.

- [`테스트버전/`](테스트버전/)

이 폴더에는 전체 산출물 중 잘 나온 샘플만 선별해 넣었습니다.

## MCP 서버 구성

MCP 서버는 로컬 허브 API를 감싸는 tool interface 역할을 합니다. 에이전트는 직접 DB를 만지는 대신 MCP tool을 호출하고, MCP 서버는 허브 API에 요청을 전달합니다.

주요 구성은 다음과 같습니다.

- `mcp_server/pm_server.py`
  - PM/오케스트레이션용 MCP 서버
  - 작업 생성, 상태 조회, 승인 패키지 생성, downstream 전달 요청을 tool 형태로 제공

- `app/main.py`
  - FastAPI 애플리케이션 진입점
  - 작업, 승인, 이미지, Unity bridge, runtime report 관련 API 라우팅

- `app/workflow.py`
  - 작업 상태 전이와 승인 루프 제어
  - 생성 → QA → 승인 대기 → 전달 가능 상태를 분리

- `app/handoff.py`
  - 에이전트/작업 채팅 간 전달 패키지 생성
  - 작업 지시와 산출물 정보를 Markdown/JSON 형태로 정리

- `app/unity_bridge.py`
  - 승인된 산출물만 Unity 전달 패키지로 변환
  - 미승인 리소스가 개발 단계로 흘러가는 것을 방지

## 자동 작업 루프

파이프라인은 한 번의 생성으로 끝나지 않고, 결과를 다시 검수하고 다음 단계 입력으로 넘기는 루프 형태로 설계했습니다.

```text
사용자 지시
  ↓
로컬 문서/이전 산출물 분석
  ↓
작업 명세 추출
  ↓
프롬프트 및 작업 패키지 생성
  ↓
이미지 생성 또는 로컬 처리 실행
  ↓
투명화/리사이즈/스프라이트 시트 후처리
  ↓
QA 검사 및 manifest 생성
  ↓
사용자 승인 대기
  ↓
승인된 경우에만 Unity 전달 패키지 생성
```

이 구조를 둔 이유는 생성형 AI 결과물이 매번 규격, 비율, 방향, 배경, 외곽선 품질이 흔들릴 수 있기 때문입니다. 자동화가 잘못된 결과물을 곧바로 개발 단계에 반영하지 않도록, QA와 사용자 승인을 별도 게이트로 분리했습니다.

## 사용자 승인 게이트를 넣은 이유

자동화 파이프라인에서 가장 위험한 지점은 “그럴듯하지만 규격이 틀린 결과물”이 다음 단계로 넘어가는 것입니다. 특히 이미지 에셋은 Unity prefab, atlas, animation controller에 한 번 반영되면 되돌리는 비용이 커집니다.

승인 게이트는 다음 문제를 막기 위해 설계했습니다.

- 잘못된 프레임 수나 셀 크기의 시트가 등록되는 문제
- pivot, baseline, center alignment가 맞지 않는 리소스가 downstream으로 전달되는 문제
- 크로마키 잔여물, 투명화 실패, 외곽선 오염이 있는 PNG가 반영되는 문제
- 사용자가 승인하지 않은 디자인 방향이 개발 리소스에 섞이는 문제
- 자동 루프가 오류 결과물을 반복 확산시키는 문제

따라서 이 프로젝트는 `자동 생성`보다 `검수 가능한 자동화`에 초점을 두었습니다.

## 로컬 기반 환경 활용

외부 API 의존도를 낮추고 재현 가능한 작업 환경을 만들기 위해 로컬 실행을 중심으로 구성했습니다.

- Ollama 로컬 LLM
  - 문서 요약, 작업 명세 정리, 프롬프트 초안 작성, QA 체크리스트 구성에 활용
  - 네트워크 장애 및 API 비용 영향을 줄이기 위한 로컬 추론 환경

- Python
  - 이미지 후처리 스크립트, manifest 생성, 파일 검증, 자동 등록 도구 구현

- Pillow
  - RGBA 변환, 크로마키 제거, 알파 채널 검증
  - bounding box 추출, sprite cell 배치, GIF 미리보기 생성

- 로컬 파일 시스템
  - 원본, 중간 산출물, 최종 PNG/GIF, QA report를 프로젝트 폴더 아래에 저장
  - manifest에 경로와 검수 결과를 기록해 추적성 확보

## 이미지/스프라이트 후처리 자동화

생성형 이미지 결과물을 그대로 쓰지 않고, 로컬 후처리 과정을 거쳐 프로젝트 리소스로 변환했습니다.

주요 처리 단계:

1. 생성 결과 파일 탐색
2. 프로젝트 작업 폴더로 복사
3. 크로마키 배경 제거
4. 알파 채널 기반 투명 PNG 생성
5. 외곽선 잔여 픽셀 제거/despill
6. 캐릭터 bounding box 추출
7. 셀 내부 안전 여백 확보
8. 기준선 및 중심축 정렬
9. sprite sheet 생성
10. 6fps GIF 미리보기 생성
11. QA manifest JSON 생성

## QA Manifest

각 산출물은 JSON manifest로 기록합니다.

기록 항목 예시:

- asset id
- source file
- output paths
- sprite sheet size
- grid size
- cell size
- frame count
- fps
- pivot
- baseline/center alignment
- transparent background 여부
- QA pass/fail
- Unity handoff 가능 여부

manifest를 사용하는 이유는 사람이 이미지를 일일이 열어보지 않아도 산출물 상태와 전달 가능 여부를 추적하기 위해서입니다.

## 스프라이트 규격 예시

프로젝트 진행 중 모바일 환경과 반복 제작 효율을 고려해 스프라이트 규격을 표준화했습니다.

```text
character/monster proportion: 2-head SD
direction: left/right side-view
sheet: 1024x512 PNG
grid: 4x2
cell: 256x256
frames: 8
preview: 6fps GIF
background: transparent
pivot: bottom-center (0.5, 1.0)
```

이 규격은 메모리 사용량, 제작 속도, 애니메이션 컨트롤러 단순화, 모바일 화면 가독성을 고려해 선택했습니다.

## 실행

Docker Desktop 실행 후:

```powershell
docker compose up --build -d
docker compose ps
```

대시보드:

```text
http://127.0.0.1:8000
```

API 문서:

```text
http://127.0.0.1:8000/docs
```

상태 확인:

```text
http://127.0.0.1:8000/health
```

종료:

```powershell
docker compose down
```

## 로컬 개발

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:DATABASE_URL="sqlite:///./data/control_hub.db"
uvicorn app.main:app --reload
```

테스트:

```powershell
python -m pytest -q
```

## MCP PM 서버 실행

```powershell
$env:GAME_HUB_URL="http://127.0.0.1:8000"
python -m mcp_server.pm_server
```

## 기술 키워드

`MCP`, `FastAPI`, `Python`, `Pillow`, `Ollama`, `Local LLM`, `Docker Compose`, `PostgreSQL`, `SQLite`, `Workflow Automation`, `Human-in-the-loop Approval`, `JSON Manifest`, `Sprite Sheet QA`, `Local-first AI Pipeline`

## 설계 의도

이 프로젝트는 AI를 단순 보조 도구로 쓰는 것이 아니라, 작업 상태와 산출물 품질을 추적 가능한 자동화 시스템으로 묶는 실험입니다.

핵심 설계 원칙은 다음과 같습니다.

- 반복 작업은 자동화한다.
- 품질 판단은 QA와 사용자 승인으로 분리한다.
- 외부 API 의존도를 낮추고 로컬에서 재현 가능하게 만든다.
- 산출물은 manifest로 추적한다.
- 승인되지 않은 결과물은 개발 단계로 전달하지 않는다.
