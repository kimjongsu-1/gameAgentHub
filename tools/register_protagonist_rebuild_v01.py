from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
WORK = ROOT / "05_sprites/work/CHR_PROTAGONIST_REBUILD_V01"
REPORT = WORK / "CHR_PROTAGONIST_REBUILD_V01_walk_stability_strict.json"
SHEET = WORK / "CHR_PROTAGONIST_REBUILD_V01_walk_16f_4x4_stable.png"
GIF = WORK / "CHR_PROTAGONIST_REBUILD_V01_walk_6fps_stable.gif"
GUIDE = WORK / "CHR_PROTAGONIST_REBUILD_V01_walk_axis_guide_stable.png"
MANIFEST = WORK / "CHR_PROTAGONIST_REBUILD_V01_MANIFEST.json"
ASSET_ID = "CHR_PROTAGONIST_REBUILD_V01_WALK_SOUTH"
TITLE = "주인공 캐릭터 완전 재제작 V01 · 걷기 16프레임"


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json; charset=utf-8"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if report["status"] != "PASS":
        raise RuntimeError("Strict protagonist stability QA did not pass")
    manifest = {
        "asset_id": ASSET_ID,
        "character_id": "CHR_PROTAGONIST_REBUILD_V01",
        "version": "V01",
        "replacement_for": "CHR_PROTAGONIST_BASE_01_2HEAD_WALK_SOUTH_V07",
        "production_prompt": "new canonical identity; strict SD 2-head; fixed south quarter-view; no candidate blending",
        "animations": [{
            "motion": "walk",
            "motion_label": "걷기",
            "sheet_path": relative(SHEET),
            "gif_path": relative(GIF),
            "guide_path": relative(GUIDE),
            "qa_path": relative(REPORT),
            "frames": 16,
            "fps": 6,
            "qa_status": "PASS",
        }],
        "strict_metrics": {key: report[key] for key in (
            "mass_center_x_range_px", "head_center_x_range_px", "torso_center_x_range_px",
            "height_variation_percent", "minimum_safe_margin",
        )},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    assets = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    if ASSET_ID not in assets:
        call("POST", "/api/assets", {
            "asset_id": ASSET_ID,
            "asset_type": "SPRITE_SHEET",
            "character_version": "protagonist_rebuild_v01",
            "style_version": "art_bible_v03_strict_2head",
            "source_asset": "04_concepts/work/CHR_PROTAGONIST_REBUILD_V01/CHR_PROTAGONIST_REBUILD_V01_reference_chroma.png",
            "file_path": relative(SHEET),
            "frame_count": 16,
            "fps": 6,
            "loop": True,
            "pivot": {"x": 0.5, "y": 1.0},
            "status": "QA_PASS",
            "checksum": checksum(SHEET),
            "created_by": "design_orchestra_builtin_imagegen_strict_local_qa",
            "metadata": {"gif_path": relative(GIF), "guide_path": relative(GUIDE), "qa_path": relative(REPORT), "strict_metrics": manifest["strict_metrics"]},
        })

    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    task = tasks.get(TITLE)
    if task is None:
        task = call("POST", "/api/tasks", {"title": TITLE, "task_type": "protagonist_rebuild_strict_walk", "assignee_role": "design_orchestra_entity", "priority": 10, "input_payload": {"reason": "user_reported_severe_visual_jitter", "replacement_for": manifest["replacement_for"]}})
    output = {"manifest_path": relative(MANIFEST), "asset_ids": [ASSET_ID], "preview_paths": [relative(GIF), relative(GUIDE)], "qa": {"status": "PASS", **manifest["strict_metrics"]}}
    call("PATCH", f"/api/tasks/{task['id']}/status", {"status": "WAITING_USER_APPROVAL", "output_payload": output})
    pending = call("GET", "/api/approvals?status=PENDING&limit=500")
    approval = next((item for item in pending if item["task_id"] == task["id"]), None)
    if approval is None:
        approval = call("POST", "/api/approvals", {"task_id": task["id"], "approval_type": "PROTAGONIST_REBUILD_V01", "summary": "기존 주인공을 사용하지 않고 새 기준 원화부터 재제작한 16프레임 6fps 걷기입니다. 머리·몸통·전체 중심 및 크기 강화 QA PASS.", "preview_paths": [relative(GIF), relative(GUIDE)], "recommendation": "APPROVE", "asset_ids": [ASSET_ID]})
    print(json.dumps({"task_id": task["id"], "approval_id": approval["id"], "asset_id": ASSET_ID, "status": "WAITING_USER_APPROVAL"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
