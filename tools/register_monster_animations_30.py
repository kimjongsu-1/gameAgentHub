from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
ANIMATION_ROOT = ROOT / "05_sprites/work/MONSTER_30_ANIMATIONS"
MANIFEST = ANIMATION_ROOT / "MONSTER_30_ANIMATION_MANIFEST.json"
TITLE = "몬스터 30종 RUN · HIT · ATTACK 90시트"


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not manifest["all_qa_pass"]:
        raise RuntimeError("animation manifest contains QA failures")

    existing = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    asset_ids = []
    for entry in manifest["entries"]:
        asset_id = entry["asset_id"]
        asset_ids.append(asset_id)
        if asset_id in existing:
            continue
        existing[asset_id] = call(
            "POST",
            "/api/assets",
            {
                "asset_id": asset_id,
                "asset_type": "SPRITE_SHEET",
                "character_version": entry["monster_id"].lower(),
                "style_version": "art_bible_v02_axis_locked_" + entry["motion"],
                "source_asset": f"04_concepts/work/MONSTER_30_CATALOG/variants/{entry['monster_id']}.png",
                "file_path": entry["sheet_path"],
                "frame_count": 16,
                "fps": 6,
                "loop": True,
                "pivot": {"x": 0.5, "y": 1.0},
                "status": "QA_PASS",
                "checksum": checksum(ROOT / entry["sheet_path"]),
                "created_by": "local_free_qa_animation_pipeline",
                "metadata": {
                    "monster_id": entry["monster_id"],
                    "family": entry["family"],
                    "palette": entry["palette"],
                    "motion": entry["motion"],
                    "gif_path": entry["gif_path"],
                    "qa_path": entry["qa_path"],
                    "body_center_x_range_px": entry["qa"]["body_center_x_range_px"],
                    "baseline_range_px": entry["qa"]["baseline_range_px"],
                    "minimum_safe_margin": entry["qa"]["minimum_safe_margin"],
                    "cell_invasion": entry["qa"]["cell_invasion"],
                },
            },
        )

    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    task = tasks.get(TITLE)
    if task is None:
        task = call(
            "POST",
            "/api/tasks",
            {
                "title": TITLE,
                "task_type": "monster_animation_90_sheets",
                "assignee_role": "design_orchestra",
                "priority": 20,
                "input_payload": {
                    "monster_count": 30,
                    "motions": ["run", "hit", "attack"],
                    "sheet_count": 90,
                    "sheet_size": "1024x1024",
                    "cell_size": "256x256",
                    "frame_count": 16,
                    "fps": 6,
                    "horizontal_drift_limit_px": 0.25,
                },
            },
        )

    previews = [
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_RUN_6FPS_PREVIEW.gif",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_HIT_6FPS_PREVIEW.gif",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_ATTACK_6FPS_PREVIEW.gif",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_RUN_CATALOG.png",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_HIT_CATALOG.png",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_ATTACK_CATALOG.png",
    ]
    output_payload = {
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "preview_paths": previews,
        "asset_ids": asset_ids,
        "qa": {
            "status": "PASS",
            "total_sheets": 90,
            "max_horizontal_drift_px": manifest["max_horizontal_drift_px"],
            "all_qa_pass": manifest["all_qa_pass"],
            "sheet_standard": manifest["sheet_standard"],
        },
    }
    call("PATCH", f"/api/tasks/{task['id']}/status", {"status": "WAITING_USER_APPROVAL", "output_payload": output_payload})

    pending = call("GET", "/api/approvals?status=PENDING&limit=500")
    if not any(item["task_id"] == task["id"] for item in pending):
        call(
            "POST",
            "/api/approvals",
            {
                "task_id": task["id"],
                "approval_type": "MONSTER_RUN_HIT_ATTACK_AXIS_LOCKED",
                "summary": f"몬스터 30종 × run/hit/attack = 90시트. 캐릭터 공통 규격 적용, 좌우 중심 최대 편차 {manifest['max_horizontal_drift_px']}px, 전 시트 QA PASS.",
                "preview_paths": previews,
                "recommendation": "APPROVE",
                "asset_ids": asset_ids,
            },
        )
    print(json.dumps({"task_id": task["id"], "assets": len(asset_ids), "status": "WAITING_USER_APPROVAL", "max_horizontal_drift_px": manifest["max_horizontal_drift_px"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
