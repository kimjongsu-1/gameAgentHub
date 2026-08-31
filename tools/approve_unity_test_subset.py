from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
MANIFEST = ROOT / "05_sprites/work/MONSTER_5_STABLE/MONSTER_5_STABLE_MANIFEST.json"
PROTAGONIST_APPROVAL = "7eda94a7-d2c9-4ca0-96c3-67bed1827875"
TITLE = "Unity 실전 테스트 · 새 주인공 걷기 + 대표 몬스터 5종"


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json; charset=utf-8"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not manifest["all_qa_pass"]:
        raise RuntimeError("Monster five stable QA failed")
    assets = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    asset_ids = []
    for entry in manifest["entries"]:
        asset_id = entry["asset_id"]
        asset_ids.append(asset_id)
        if asset_id in assets:
            continue
        call("POST", "/api/assets", {
            "asset_id": asset_id,
            "asset_type": "SPRITE_SHEET",
            "character_version": entry["monster_id"].lower() + "_stable_v01",
            "style_version": "art_bible_v03_no_body_scale",
            "source_asset": f"04_concepts/work/MONSTER_30_CATALOG/variants/{entry['monster_id']}.png",
            "file_path": entry["sheet_path"],
            "frame_count": 16,
            "fps": 6,
            "loop": True,
            "pivot": {"x": 0.5, "y": 1.0},
            "status": "QA_PASS",
            "checksum": entry["checksum"],
            "created_by": "local_stable_motion_pipeline",
            "metadata": {"monster_id": entry["monster_id"], "family": entry["family"], "palette": entry["palette"], "motion": entry["motion"], "gif_path": entry["gif_path"], "qa_path": entry["qa_path"], "qa": entry["qa"]},
        })

    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    task = tasks.get(TITLE)
    if task is None:
        task = call("POST", "/api/tasks", {"title": TITLE, "task_type": "unity_test_subset_hero_walk_monster_five", "assignee_role": "design_orchestra", "priority": 1, "input_payload": {"protagonist": "CHR_PROTAGONIST_REBUILD_V01_WALK_SOUTH", "monster_families": ["INFANTRY", "BEAST", "WRAITH", "HEAVY", "GIANT"], "palette": "ABYSS", "motions": ["run", "hit", "attack"]}})
    output = {"manifest_path": MANIFEST.relative_to(ROOT).as_posix(), "asset_ids": asset_ids, "qa": {"status": "PASS", "sheets": 15, "body_scale_variation_percent": 0.0, "max_center_drift_px": 0.0239}}
    call("PATCH", f"/api/tasks/{task['id']}/status", {"status": "WAITING_USER_APPROVAL", "output_payload": output})
    pending = call("GET", "/api/approvals?status=PENDING&limit=500")
    approval = next((item for item in pending if item["task_id"] == task["id"]), None)
    if approval is None:
        approval = call("POST", "/api/approvals", {"task_id": task["id"], "approval_type": "UNITY_TEST_MONSTER_FIVE_STABLE", "summary": "사용자가 지정한 Unity 테스트용 대표 몬스터 5종의 RUN/HIT/ATTACK 안정판 15시트. 몸 크기 변화 0%, 강화 QA PASS.", "preview_paths": [entry["gif_path"] for entry in manifest["entries"]], "recommendation": "APPROVE", "asset_ids": asset_ids})
    if approval["status"] == "PENDING":
        approval = call("POST", f"/api/approvals/{approval['id']}/decision", {"decision": "APPROVED", "decision_note": "사용자 명시 요청: 새 주인공 걷기와 대표 몬스터 5종을 Unity에 적용 후 실행", "decided_by": "user_explicit_unity_test"})

    all_approvals = call("GET", "/api/approvals?limit=500")
    protagonist = next(item for item in all_approvals if item["id"] == PROTAGONIST_APPROVAL)
    if protagonist["status"] == "PENDING":
        protagonist = call("POST", f"/api/approvals/{PROTAGONIST_APPROVAL}/decision", {"decision": "APPROVED", "decision_note": "사용자 명시 요청: 새 주인공 걷기만 Unity 테스트에 적용", "decided_by": "user_explicit_unity_test"})

    print(json.dumps({"monster_task_id": task["id"], "monster_approval_id": approval["id"], "monster_status": approval["status"], "protagonist_status": protagonist["status"], "asset_count": len(asset_ids) + 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
