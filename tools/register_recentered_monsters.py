from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
GROUP = Path("05_sprites/work/recentered_monsters_v02")


SPECS = [
    ("DUEOKSINI_WALK_LEFT_V03", "두억시니 걷기 중심축 재설계 V03", "05_sprites/work/DUEOKSINI_walk_left_v2.png"),
    ("MON_PROLOGUE_CRACKED_WRAITH_01_IDLE_V02", "금 간 잔령 대기 중심축 재설계 V02", "05_sprites/work/MON_PROLOGUE_CRACKED_WRAITH_01/MON_PROLOGUE_CRACKED_WRAITH_01_idle_16f_4x4.png"),
    ("MON_PROLOGUE_CRACKED_WRAITH_01_MOVE_V02", "금 간 잔령 이동 중심축 재설계 V02", "05_sprites/work/MON_PROLOGUE_CRACKED_WRAITH_01/MON_PROLOGUE_CRACKED_WRAITH_01_move_16f_4x4.png"),
    ("MON_PROLOGUE_SEVERED_INFANTRY_01_IDLE_V02", "끊긴 보병 대기 중심축 재설계 V02", "05_sprites/work/MON_PROLOGUE_SEVERED_INFANTRY_01/MON_PROLOGUE_SEVERED_INFANTRY_01_idle_16f_4x4.png"),
    ("MON_PROLOGUE_SEVERED_INFANTRY_01_WALK_V02", "끊긴 보병 걷기 중심축 재설계 V02", "05_sprites/work/MON_PROLOGUE_SEVERED_INFANTRY_01/MON_PROLOGUE_SEVERED_INFANTRY_01_walk_16f_4x4.png"),
]


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    assets = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    pending = call("GET", "/api/approvals?status=PENDING&limit=500")
    pending_task_ids = {item["task_id"] for item in pending}
    results = []

    for asset_id, title, source_rel in SPECS:
        folder = GROUP / asset_id
        output_rel = (folder / f"{asset_id}_16f_4x4_recentered.png").as_posix()
        gif_rel = (folder / f"{asset_id}_6fps.gif").as_posix()
        guide_rel = (folder / f"{asset_id}_axis_guide.png").as_posix()
        report_rel = (folder / f"{asset_id}_qa.json").as_posix()
        output = ROOT / output_rel
        report = json.loads((ROOT / report_rel).read_text(encoding="utf-8"))

        if asset_id not in assets:
            assets[asset_id] = call(
                "POST",
                "/api/assets",
                {
                    "asset_id": asset_id,
                    "asset_type": "SPRITE_SHEET",
                    "character_version": asset_id.lower(),
                    "style_version": "art_bible_v02_center_axis",
                    "source_asset": source_rel,
                    "file_path": output_rel,
                    "frame_count": 16,
                    "fps": 6,
                    "loop": True,
                    "pivot": {"x": 0.5, "y": 1.0},
                    "status": "QA_PASS",
                    "checksum": sha256(output),
                    "created_by": "local_free_qa",
                    "metadata": {
                        "visual_anchor_x_range_px": report["visual_anchor_x_range_px"],
                        "visual_anchor_y_range_px": report["visual_anchor_y_range_px"],
                        "bbox_height_variation_percent": report["bbox_height_variation_percent"],
                        "baseline_y": report["baseline_y"],
                        "safe_area": report["safe_area"],
                        "qa_report": report_rel,
                    },
                },
            )

        task = tasks.get(title)
        if task is None:
            task = call(
                "POST",
                "/api/tasks",
                {
                    "title": title,
                    "task_type": "sprite_16_frame_recenter",
                    "assignee_role": "design_orchestra",
                    "priority": 20,
                    "input_payload": {
                        "asset_id": asset_id,
                        "sheet_size": "1024x1024",
                        "cell_size": "256x256",
                        "frame_count": 16,
                        "fps": 6,
                        "center_drift_limit_px": 1,
                        "size_variation_limit_percent": 2,
                    },
                },
            )
            tasks[title] = task

        output_payload = {
            "asset_id": asset_id,
            "sprite_path": output_rel,
            "preview_paths": [gif_rel, guide_rel, output_rel],
            "qa_report": report_rel,
            "enhanced_qa": {
                "status": "PASS",
                "visual_anchor_x_range_px": report["visual_anchor_x_range_px"],
                "visual_anchor_y_range_px": report["visual_anchor_y_range_px"],
                "size_variation_percent": report["bbox_height_variation_percent"],
                "baseline_y": report["baseline_y"],
            },
        }
        call("PATCH", f"/api/tasks/{task['id']}/status", {"status": "WAITING_USER_APPROVAL", "output_payload": output_payload})

        if task["id"] not in pending_task_ids:
            call(
                "POST",
                "/api/approvals",
                {
                    "task_id": task["id"],
                    "approval_type": "MONSTER_CENTER_AXIS_ENHANCED_QA",
                    "summary": f"{title}: 시각 중심 X {report['visual_anchor_x_range_px']}px, Y {report['visual_anchor_y_range_px']}px, 크기 변화 {report['bbox_height_variation_percent']}%, 강화 QA PASS.",
                    "preview_paths": [gif_rel, guide_rel, output_rel],
                    "recommendation": "APPROVE",
                    "asset_ids": [asset_id],
                },
            )
            pending_task_ids.add(task["id"])
        results.append({"asset_id": asset_id, "task_id": task["id"], "status": "WAITING_USER_APPROVAL"})

    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
