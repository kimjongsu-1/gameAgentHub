import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import app
from app.unity_bridge import UnityBridgeError, UnityImportConfig, sha256_file, stage_unity_import


def make_approved_files(root: Path, status: str = "APPROVED") -> tuple[Path, Path]:
    sprite = root / "05_sprites" / "approved" / "walk.png"
    sprite.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (256, 256), (20, 90, 190, 255)).save(sprite)
    manifest = root / "manifests" / "CHR_TEST_WALK.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "asset_id": "CHR_TEST_WALK",
                "status": status,
                "file_path": "05_sprites/approved/walk.png",
                "checksum": sha256_file(sprite),
                "character_version": "test_v01",
                "style_version": "style_v01",
            }
        ),
        encoding="utf-8",
    )
    qa = root / "05_sprites" / "qa" / "walk" / "qa_result.json"
    qa.parent.mkdir(parents=True, exist_ok=True)
    qa.write_text(json.dumps({"status": "PASS", "source_path": sprite.as_posix()}), encoding="utf-8")
    return manifest, qa


def test_stage_approved_unity_package(tmp_path):
    manifest, qa = make_approved_files(tmp_path)
    receipt = stage_unity_import(
        manifest,
        qa,
        tmp_path / "06_game" / "approved_imports",
        UnityImportConfig(resource_name="HeroWalk"),
    )
    request = json.loads(Path(receipt["request_path"]).read_text(encoding="utf-8"))
    assert request["status"] == "APPROVED"
    assert request["qa_status"] == "PASS"
    assert request["resource_name"] == "HeroWalk"
    assert Path(receipt["source_path"]).is_file()


def test_stage_accepts_legacy_checksum_without_prefix(tmp_path):
    manifest, qa = make_approved_files(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["checksum"] = payload["checksum"].removeprefix("sha256:")
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    receipt = stage_unity_import(
        manifest,
        qa,
        tmp_path / "06_game" / "legacy_checksum_import",
        UnityImportConfig(resource_name="LegacyChecksumWalk"),
    )
    assert Path(receipt["source_path"]).is_file()


def test_unity_staging_rejects_unapproved_asset(tmp_path):
    manifest, qa = make_approved_files(tmp_path, status="QA_PASS")
    with pytest.raises(UnityBridgeError, match="APPROVED"):
        stage_unity_import(
            manifest,
            qa,
            tmp_path / "06_game" / "approved_imports",
            UnityImportConfig(resource_name="HeroWalk"),
        )


def test_runtime_report_updates_game_task():
    root = get_settings().resolved_workspace_root
    report_path = root / "08_runtime_captures" / "approved-import-test.json"
    capture_path = root / "08_runtime_captures" / "test.png"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"asset_id": "CHR_TEST_WALK", "status": "SUCCESS", "imported_frames": 16}),
        encoding="utf-8",
    )
    Image.new("RGB", (64, 64), (20, 30, 40)).save(capture_path)
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "Unity 걷기 적용",
                "task_type": "unity_integration",
                "assignee_role": "game_development",
            },
        ).json()
        response = client.post(
            "/api/runtime-reports",
            json={
                "task_id": task["id"],
                "report_path": "08_runtime_captures/approved-import-test.json",
                "capture_paths": ["08_runtime_captures/test.png"],
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "PASS"
        tasks = {item["id"]: item for item in client.get("/api/tasks").json()}
        assert tasks[task["id"]]["status"] == "RUNTIME_QA"
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["runtime_counts"]["PASS"] >= 1


def test_unity_bridge_setup_can_be_queued_once():
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={
                "title": "Unity Bridge 설치",
                "task_type": "unity_bridge_setup",
                "assignee_role": "game_development",
                "input_payload": {"bridge_source": "06_game/unity_bridge/Editor/ApprovedAssetImporter.cs"},
            },
        ).json()
        queued = client.post(f"/api/tasks/{task['id']}/queue-dispatch")
        assert queued.status_code == 201
        assert queued.json()["target_thread_title"] == "게임개발"
        assert client.post(f"/api/tasks/{task['id']}/queue-dispatch").status_code == 409
