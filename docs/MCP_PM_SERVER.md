# MCP 총괄 PM 서버

`mcp_server/pm_server.py`는 게임 제작 통합 허브를 MCP tool로 노출하는 총괄 PM 서버입니다.

FastAPI 허브가 DB, 승인, QA, dispatch, Unity staging 상태를 관리하고, MCP 서버는 Codex가 호출할 수 있는 안전한 PM tool 표면을 제공합니다.

## 실행

허브가 먼저 떠 있어야 합니다.

```powershell
docker compose up -d
$env:GAME_HUB_URL="http://127.0.0.1:8000"
python -m mcp_server.pm_server
```

## 제공 tool

- `get_pipeline_status`
- `get_pipeline_controls`
- `get_pm_routing_architecture`
- `list_workers`
- `create_pipeline_task`
- `create_handoff_package`
- `queue_dispatch`
- `list_pending_dispatches`
- `claim_dispatch`
- `mark_dispatch_sent`
- `mark_dispatch_failed`
- `pause_pipeline_role`
- `resume_pipeline_role`
- `register_runtime_report`
- `get_gateway_policy`

## 역할 분리

- `planning_research`: 게임 기획, 자료조사, 시스템/세계관/경제 기획
- `design_orchestra`: 캐릭터 디자인, 16프레임 스프라이트, 애니메이션 소스
- `game_development`: Unity 적용, 런타임 QA, 빌드

총괄 PM은 MCP tool로 작업을 만들고, 허브는 대시보드와 상태 저장소로 사용합니다.
