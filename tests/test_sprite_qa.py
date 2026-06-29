import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import get_settings
from app.main import app
from app.sprite_qa import QAConfig, run_sprite_qa


def make_sheet(path: Path, green_background: bool = False) -> None:
    cell = 64
    background = (0, 255, 0, 255) if green_background else (0, 0, 0, 0)
    sheet = Image.new("RGBA", (cell * 4, cell * 4), background)
    for index in range(16):
        frame = Image.new("RGBA", (cell, cell), background)
        draw = ImageDraw.Draw(frame)
        draw.rectangle((20, 10, 43, 55), fill=(45, 115, 220, 255))
        draw.point((22 + index % 12, 20 + index // 12), fill=(255, 180, index * 8, 255))
        sheet.alpha_composite(frame, ((index % 4) * cell, (index // 4) * cell))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def test_sprite_qa_generates_all_outputs(tmp_path):
    source = tmp_path / "walk.png"
    output = tmp_path / "qa"
    make_sheet(source)
    result = run_sprite_qa(source, output, QAConfig())
    assert result["status"] == "PASS"
    for filename in ("preview.gif", "contact_sheet.png", "onion_skin.gif", "qa_report.md", "qa_result.json"):
        assert (output / filename).is_file()
    assert json.loads((output / "qa_result.json").read_text(encoding="utf-8"))["frame_count"] == 16


def test_sprite_qa_api_updates_task_and_asset():
    root = get_settings().resolved_workspace_root
    source = root / "05_sprites" / "work" / "green_walk.png"
    make_sheet(source, green_background=True)
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "초록 배경 걷기 QA",
                "task_type": "sprite_16_frame",
                "assignee_role": "design_orchestra",
            },
        ).json()
        asset = client.post(
            "/api/assets",
            json={
                "asset_id": "CHR_TEST_GREEN_WALK_001",
                "asset_type": "SPRITE_SHEET",
                "character_version": "test_v01",
                "style_version": "test_style_v01",
                "source_asset": "master.png",
                "file_path": "05_sprites/work/green_walk.png",
                "frame_count": 16,
                "fps": 12,
                "loop": True,
                "status": "WORKING",
                "checksum": "sha256:test",
                "created_by": "design_orchestra",
            },
        ).json()

        response = client.post(
            "/api/sprite-qa/run",
            json={
                "source_path": "05_sprites/work/green_walk.png",
                "output_dir": "05_sprites/qa/green_walk",
                "task_id": task["id"],
                "asset_id": asset["asset_id"],
                "chroma_key": "#00ff00",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "PASS"
        tasks = {item["id"]: item for item in client.get("/api/tasks").json()}
        assert tasks[task["id"]]["status"] == "WAITING_USER_APPROVAL"
        assets = {item["asset_id"]: item for item in client.get("/api/assets").json()}
        assert assets[asset["asset_id"]]["status"] == "QA_PASS"


def test_handoff_package_targets_design_thread():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "구미호 공격 16프레임",
                "task_type": "sprite_16_frame",
                "assignee_role": "design_orchestra",
                "input_payload": {"character": "구미호", "motion": "attack"},
            },
        ).json()
        response = client.post(f"/api/tasks/{task['id']}/handoff-package")
        assert response.status_code == 200
        package = response.json()
        assert package["target_thread_title"] == "게임 개발 디자인"
        assert "정확히 16프레임" in package["prompt"]
        assert (get_settings().resolved_workspace_root / package["json_path"]).is_file()


def test_sprite_qa_rejects_path_outside_workspace():
    with TestClient(app) as client:
        response = client.post("/api/sprite-qa/run", json={"source_path": "../outside.png"})
        assert response.status_code == 400


def test_approved_qa_pass_queues_and_completes_game_dispatch():
    root = get_settings().resolved_workspace_root
    preview = root / "05_sprites" / "qa" / "approved_walk" / "contact_sheet.png"
    make_sheet(preview)
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "승인된 걷기 모션",
                "task_type": "sprite_16_frame",
                "assignee_role": "design_orchestra",
            },
        ).json()
        client.patch(
            f"/api/tasks/{task['id']}/status",
            json={
                "status": "WAITING_USER_APPROVAL",
                "output_payload": {
                    "sprite_qa": {
                        "status": "PASS",
                        "outputs": {"contact_sheet": "05_sprites/qa/approved_walk/contact_sheet.png"},
                    }
                },
            },
        )
        approval = client.post(
            "/api/approvals",
            json={
                "task_id": task["id"],
                "approval_type": "SPRITE_GIF",
                "summary": "게임 적용 전 최종 승인",
                "preview_paths": ["05_sprites/qa/approved_walk/contact_sheet.png"],
            },
        ).json()
        decision = client.post(
            f"/api/approvals/{approval['id']}/decision",
            json={"decision": "APPROVED", "decided_by": "user"},
        )
        assert decision.status_code == 200
        assert client.post(
            f"/api/approvals/{approval['id']}/decision",
            json={"decision": "APPROVED", "decided_by": "user"},
        ).status_code == 409

        dispatches = client.get("/api/dispatches", params={"status": "PENDING"}).json()
        assert len(dispatches) == 1
        dispatch = dispatches[0]
        assert dispatch["target_thread_title"] == "게임개발"
        assert "QA_PASS" not in dispatch["prompt"]
        assert "승인된 입력 에셋만 사용하세요" in dispatch["prompt"]

        claimed = client.post(f"/api/dispatches/{dispatch['id']}/claim")
        assert claimed.json()["status"] == "CLAIMED"
        sent = client.patch(f"/api/dispatches/{dispatch['id']}", json={"status": "SENT"})
        assert sent.json()["status"] == "SENT"
        tasks = {item["id"]: item for item in client.get("/api/tasks").json()}
        assert tasks[dispatch["target_task_id"]]["status"] == "RUNNING"

        preview_response = client.get("/workspace-files/05_sprites/qa/approved_walk/contact_sheet.png")
        assert preview_response.status_code == 200
        assert preview_response.headers["content-type"] == "image/png"
