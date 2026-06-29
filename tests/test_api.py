from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import app


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
)


def valid_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_and_agents():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        agents = client.get("/api/agents").json()
        assert agents["orchestrator"]["thread_title"] == "게임 제작 통합 파이프라인 구축"
        assert agents["planning"]["mode"] == "user_direct"
        assert agents["qa"]["mode"] == "free_local_tools"
        assert {worker["role"] for worker in agents["workers"]} == {
            "design_orchestra",
            "game_development",
        }
        assert {worker["thread_title"] for worker in agents["workers"]} >= {
            "게임 개발 디자인",
            "게임개발",
        }


def test_design_handoff_package_documents_user_planning_and_local_qa():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "방치형 RPG 주인공 16프레임 제작",
                "task_type": "sprite_16_frame",
                "assignee_role": "design_orchestra",
                "input_payload": {"user_planning": "검을 쓰는 도깨비 주인공", "frame_count": 16},
            },
        ).json()
        response = client.post(f"/api/tasks/{task['id']}/handoff-package")
        assert response.status_code == 200
        package = response.json()
        assert package["target_thread_title"] == "게임 개발 디자인"
        assert "기획/자료조사는 사용자가 직접 제공한 내용" in package["prompt"]
        assert "반복 검사는 무료 로컬 QA" in package["prompt"]
        assert "발바닥 기준점은 모든 프레임에서 같은 y좌표" in package["prompt"]
        assert "프레임 위치가 흔들리면 재작업 대상" in package["prompt"]


def test_task_approval_flow_without_linked_game_asset():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "도깨비 걷기 모션",
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
                "summary": "16프레임 걷기 모션 검토",
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


def test_super_grok_animation_prompt_package_from_character_image():
    workspace = get_settings().resolved_workspace_root
    image_path = workspace / "03_character_masters" / "hero.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(PNG_1X1)

    with TestClient(app) as client:
        response = client.post(
            "/api/super-grok/animation-prompts",
            json={
                "title": "Hero slash skill animation",
                "request_type": "skill_animation",
                "reference_image_path": "03_character_masters/hero.png",
                "character_name": "Hero",
                "animation_goal": "Create a fast sword slash with anticipation, impact flash, and recovery pose.",
                "style_notes": "2D mobile idle RPG, clean silhouette, simple background.",
                "duration_seconds": 2.5,
                "aspect_ratio": "1:1",
            },
        )
        assert response.status_code == 201
        package = response.json()
        assert package["status"] == "READY"
        assert package["reference_image_path"] == "03_character_masters/hero.png"
        assert "Use the attached single reference image" in package["prompt"]
        assert "Do not redesign the character" in package["negative_prompt"]
        assert (workspace / package["package_path"]).is_file()

        dashboard = client.get("/api/dashboard").json()
        assert dashboard["recent_super_grok_prompts"][0]["id"] == package["id"]


def test_character_consistency_upload_creates_design_dispatch():
    with TestClient(app) as client:
        response = client.post(
            "/api/design/character-consistency-tests",
            data={
                "character_name": "두억시니 보스",
                "notes": "붉은 눈, 뿔, 도깨비 방망이, 남색 의상 유지",
                "variants": "4",
            },
            files={"file": ("dueoksini_reference.png", valid_png_bytes(), "image/png")},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["reference_image_path"].startswith("03_character_masters/uploads/")
        assert payload["task"]["assignee_role"] == "design_orchestra"
        assert payload["task"]["task_type"] == "character_consistency_test"
        assert payload["dispatch"]["status"] == "PENDING"
        assert payload["dispatch"]["target_thread_title"] == "게임 개발 디자인"
        prompt = payload["handoff_package"]["prompt"]
        assert "참조 일러스트 1장" in prompt
        assert "캐릭터 정체성이 통일" in prompt
        assert "얼굴 비율" in prompt
        assert "다른 캐릭터처럼 보이는 재해석 금지" in prompt
        dispatch_id = payload["dispatch"]["id"]
        assert client.post(f"/api/dispatches/{dispatch_id}/claim").status_code == 200
        assert client.patch(f"/api/dispatches/{dispatch_id}", json={"status": "SENT"}).status_code == 200


def test_design_consistency_upload_supports_monsters_maps_and_items():
    cases = [
        ("monster", "두억시니 졸개", "04_concepts/work/uploads/monsters/", "monster_consistency_test", "몬스터 종족"),
        ("boss_monster", "두억시니 왕", "04_concepts/work/uploads/boss_monsters/", "boss_monster_consistency_test", "보스몬스터"),
        ("map", "귀신 숲", "04_concepts/work/uploads/maps/", "map_consistency_test", "맵의 지형 구조"),
        ("item", "화염 부적", "04_concepts/work/uploads/items/", "item_consistency_test", "아이템의 형태"),
    ]
    with TestClient(app) as client:
        for asset_kind, asset_name, prefix, task_type, prompt_marker in cases:
            response = client.post(
                "/api/design/consistency-tests",
                data={
                    "asset_kind": asset_kind,
                    "asset_name": asset_name,
                    "notes": "업로드 참조와 같은 디자인으로 유지",
                    "variants": "3",
                },
                files={"file": (f"{asset_kind}.png", valid_png_bytes(), "image/png")},
            )
            assert response.status_code == 201
            payload = response.json()
            assert payload["reference_image_path"].startswith(prefix)
            assert payload["task"]["task_type"] == task_type
            assert payload["task"]["assignee_role"] == "design_orchestra"
            assert payload["dispatch"]["status"] == "PENDING"
            assert prompt_marker in payload["handoff_package"]["prompt"]
            dispatch_id = payload["dispatch"]["id"]
            assert client.post(f"/api/dispatches/{dispatch_id}/claim").status_code == 200
            assert client.patch(f"/api/dispatches/{dispatch_id}", json={"status": "SENT"}).status_code == 200


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


def test_pipeline_status_and_role_pause_resume():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "게임개발 대기 테스트",
                "task_type": "unity_bridge_setup",
                "assignee_role": "game_development",
                "input_payload": {"bridge_source": "06_game/unity_bridge/Editor/ApprovedAssetImporter.cs"},
            },
        ).json()
        client.patch(f"/api/tasks/{task['id']}/status", json={"status": "READY"})
        paused = client.post("/api/pipeline/roles/game_development/pause", params={"reason": "test_pause"})
        assert paused.status_code == 200
        assert paused.json()["paused_tasks"] >= 1
        tasks = {item["id"]: item for item in client.get("/api/tasks").json()}
        assert tasks[task["id"]]["status"] == "PAUSED"

        status = client.get("/api/pipeline/status").json()
        assert status["paused_tasks"] >= 1
        assert status["architecture"]["dispatcher_mode"] == "manual"
        assert status["architecture"]["game_development_locked"] is True
        assert status["architecture"]["planning_mode"] == "user_direct"
        assert status["architecture"]["repeated_qa_mode"] == "free_local_tools"
        assert any(stage["role"] == "user_direct_planning" and stage["configured"] for stage in status["stages"])
        assert any(stage["role"] == "local_free_qa" and stage["configured"] for stage in status["stages"])

        resumed = client.post("/api/pipeline/roles/game_development/resume")
        assert resumed.status_code == 200
        tasks = {item["id"]: item for item in client.get("/api/tasks").json()}
        assert tasks[task["id"]]["status"] == "READY"


def test_removed_planning_worker_cannot_dispatch():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "사용자 직접 기획 메모",
                "task_type": "market_research",
                "assignee_role": "planning_research",
            },
        ).json()
        response = client.post(f"/api/tasks/{task['id']}/queue-dispatch")
        assert response.status_code == 422
        assert "No worker configured" in response.json()["detail"]


def test_pipeline_architecture_documents_pm_routing():
    with TestClient(app) as client:
        response = client.get("/api/pipeline/architecture")
        assert response.status_code == 200
        data = response.json()
        assert data["pm_owner"] == "MCP server: game_production_pm"
        assert "dispatch records" in data["routing_model"]
        assert data["dispatcher_status"] == "disabled_until_user_requests"
        assert data["planning_connected"] is True
        assert data["planning_mode"] == "user_direct"
        assert data["repeated_qa_mode"] == "free_local_tools"
