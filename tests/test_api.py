from fastapi.testclient import TestClient

from app.main import app


def test_health_and_agents():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        agents = client.get("/api/agents").json()
        assert agents["orchestrator"]["thread_title"] == "게임 제작 통합 파이프라인 구축"
        assert {worker["role"] for worker in agents["workers"]} == {
            "planning_research",
            "design_orchestra",
            "game_development",
        }
        assert {worker["thread_title"] for worker in agents["workers"]} >= {
            "게임 개발 기획",
            "게임 개발 디자인",
            "게임개발",
        }


def test_planning_research_handoff_package():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "방치형 RPG 핵심 루프 조사",
                "task_type": "system_design",
                "assignee_role": "planning_research",
                "input_payload": {"genre": "mobile idle RPG", "focus": "retention loop"},
            },
        ).json()
        response = client.post(f"/api/tasks/{task['id']}/handoff-package")
        assert response.status_code == 200
        package = response.json()
        assert package["target_thread_title"] == "게임 개발 기획"
        assert "기획 조사 요약 문서" in package["prompt"]
        assert "디자인팀 전달 요구사항" in package["prompt"]


def test_task_approval_flow_without_linked_game_asset():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "두억시니 걷기 모션",
                "task_type": "sprite_16_frame",
                "assignee_role": "design_orchestra",
                "input_payload": {"frame_count": 16},
            },
        )
        assert task.status_code == 201
        task_id = task.json()["id"]

        approval = client.post(
            "/api/approvals",
            json={
                "task_id": task_id,
                "approval_type": "SPRITE_GIF",
                "summary": "16프레임 걷기 모션 검수",
                "preview_paths": ["05_sprites/qa/preview.gif"],
            },
        )
        assert approval.status_code == 201
        assert client.get("/api/tasks").json()[0]["status"] == "WAITING_USER_APPROVAL"

        decision = client.post(
            f"/api/approvals/{approval.json()['id']}/decision",
            json={"decision": "APPROVED", "decided_by": "user"},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "APPROVED"
        assert client.get("/api/tasks").json()[0]["status"] == "APPROVED"


def test_asset_uniqueness():
    asset = {
        "asset_id": "CHR_DUEOKSINI_WALK_001",
        "asset_type": "SPRITE_SHEET",
        "character_version": "dueoksini_v01",
        "style_version": "art_bible_v01",
        "source_asset": "master.png",
        "file_path": "05_sprites/work/walk.png",
        "frame_count": 16,
        "fps": 12,
        "loop": True,
        "pivot": {"x": 0.5, "y": 0.0},
        "status": "QA_PASS",
        "checksum": "sha256:example",
        "created_by": "design_orchestra",
        "metadata": {"direction": "left"},
    }
    with TestClient(app) as client:
        assert client.post("/api/assets", json=asset).status_code == 201
        assert client.post("/api/assets", json=asset).status_code == 409
        saved = client.get("/api/assets").json()[0]
        assert saved["frame_count"] == 16
        assert saved["metadata"]["direction"] == "left"


def test_gateway_policy_blocks_external_calls_by_default():
    with TestClient(app) as client:
        policy = client.get("/api/gateway/policy").json()
        assert policy["external_calls_enabled"] is False
        check = client.post(
            "/api/gateway/check",
            json={
                "provider": "openai",
                "model": "gpt-test",
                "estimated_cost_usd": 0.01,
            },
        ).json()
        assert check["allowed"] is False
        assert check["reason"] == "external_ai_calls_disabled"
