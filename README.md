# 게임 제작 통합 허브

1인 모바일 방치형 게임의 디자인, 16프레임 스프라이트, QA, 사용자 승인, Unity 적용을 하나의 상태 기반 파이프라인으로 관리하는 로컬 허브입니다.

## 현재 범위

- FastAPI 작업·에셋·승인·API 사용량 API
- PostgreSQL 영속 저장소와 Docker Compose
- SQLite 기반 단독 실행 폴백
- 기존 Codex 채팅의 고유 스레드 ID 라우팅
- 승인 대기와 월간 API 비용을 보여주는 대시보드
- 4×4 16프레임 Sprite QA와 GIF·컨택트시트·어니언스킨 생성
- 디자인/게임개발 채팅용 표준 전달 패키지 생성
- 미리보기 기반 승인·재작업·거절 UI
- QA PASS와 사용자 승인을 모두 요구하는 게임개발 전달 큐
- 승인 manifest와 체크섬을 검증하는 Unity Import 패키지
- Unity Import·런타임 결과 보고서 회수 API
- 재현 가능한 에셋 manifest JSON Schema

외부 AI API 호출과 이미지 생성은 아직 활성화하지 않았습니다. 채팅 자동 전송 워커는 활성화되어 승인된 전달 큐를 5분 간격으로 처리합니다. Unity 프로젝트 변경은 `게임개발` 채팅이 승인 패키지를 받은 경우에만 수행합니다.

## Sprite QA

시트는 먼저 `05_sprites/work` 아래에 복사하고 워크스페이스 상대 경로로 실행합니다.

```powershell
docker compose exec api python -m app.sprite_qa `
  /workspace/05_sprites/work/character_walk.png `
  /workspace/05_sprites/qa/character_walk `
  --columns 4 --rows 4 --frames 16 --fps 12
```

초록 배경을 투명화하면서 검사할 때는 `--chroma-key "#00ff00"`를 추가합니다. 자동 투명화는 색상과 형태를 다시 그리지 않습니다.

출력:

- `preview.gif`
- `contact_sheet.png`
- `onion_skin.gif`
- `qa_report.md`
- `qa_result.json`

자동 검사는 빈 프레임, 셀 가장자리 접촉, 중복, 몸 중심·발 기준 흔들림, 크기 변화를 확인합니다. 얼굴, 의상, 무기, 타격감과 루프의 미적 완성도는 반드시 사람이 최종 확인합니다.

## 승인과 게임개발 전달

대시보드의 승인 대기 카드에서 미리보기를 확인하고 `승인`, `재작업`, `거절`을 선택합니다.

게임개발 전달 큐는 다음 조건을 모두 만족할 때만 생성됩니다.

1. 승인 유형이 16프레임 게임 에셋 유형일 것
2. Sprite QA 결과가 `PASS`일 것
3. 사용자가 대시보드에서 최종 승인할 것

전달 큐는 중복 승인을 거부하며, 전송 워커는 항목을 먼저 선점한 뒤 성공 시 `SENT`, 실패 시 `FAILED`로 기록합니다.

## Unity Bridge

승인된 PNG를 Unity로 보내기 전에 별도 패키지를 생성합니다. 자세한 사용법은 [06_game/unity_bridge/README.md](06_game/unity_bridge/README.md)를 참고합니다.

Unity 쪽 Import 결과 JSON과 캡처를 `08_runtime_captures`로 가져온 뒤 `/api/runtime-reports`에 등록하면 해당 게임 작업이 `RUNTIME_QA` 또는 `REVISION_REQUIRED`로 변경됩니다.

## 실행

Docker Desktop이 실행된 상태에서:

```powershell
docker compose up --build -d
docker compose ps
```

대시보드: <http://127.0.0.1:8000>

API 문서: <http://127.0.0.1:8000/docs>

상태 확인: <http://127.0.0.1:8000/health>

종료:

```powershell
docker compose down
```

데이터 볼륨까지 삭제하는 `docker compose down -v`는 운영 기록을 지우므로 사용하지 않습니다.

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

## 담당 채팅

- 총괄: 현재 `통합 제작 파이프라인 구축`
- 디자인·16프레임: 기존 `게임 개발 디자인`
- Unity 구현: 기존 `게임개발`

제목은 표시용이며 실제 라우팅은 [config/agents.json](config/agents.json)의 `thread_id`를 사용합니다.

## 안전 원칙

- API 키는 `.env`에만 두고 Git에 올리지 않습니다.
- 승인되지 않은 에셋은 Unity 또는 영상 제작에 전달하지 않습니다.
- PNG, GIF, PSD, 영상은 파일 저장소에 두고 DB에는 경로와 체크섬만 저장합니다.
- 기존 `C:\game\character_pipeline\IdleBattleUnity`와 실행 중인 픽셀 에셋 WebUI는 자동으로 수정하지 않습니다.
