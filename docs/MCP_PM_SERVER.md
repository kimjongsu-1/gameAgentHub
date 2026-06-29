# MCP 총괄 PM 서버

`mcp_server/pm_server.py`는 게임 제작 통합 허브를 MCP tool로 노출하는 총괄 PM 서버다.

MCP 서버는 별도 DB를 만들지 않는다. 로컬 FastAPI 허브 API를 호출해서 작업 생성, 상태 조회, 중지/재개, dispatch 준비, 런타임 보고서 등록, SuperGrok 수동 패키지 생성을 수행한다.

## 실행

허브가 먼저 떠 있어야 한다.

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
- `create_super_grok_animation_prompt`
- `get_gateway_policy`

## 운영 모드

- 기획/자료조사: 사용자 직접 수행
- 반복 QA: 무료 로컬 도구
- 디자인 worker: `design_orchestra`
- 게임개발 worker: `game_development`
- 외부 AI API: 기본 차단

`create_super_grok_animation_prompt`는 외부 API를 호출하지 않는다. 캐릭터 이미지 1장과 애니메이션/컷신 목표를 받아, 사용자가 SuperGrok에 직접 붙여넣을 프롬프트 패키지를 허브 대시보드에 생성한다.
