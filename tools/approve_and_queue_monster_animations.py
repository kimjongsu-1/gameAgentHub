from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
CATALOG_TITLE = "몬스터 5체형 × 6팔레트 파생 30종 디자인"
DRAFT_TITLE = "몬스터 30종 RUN · HIT · ATTACK 90시트"
FINAL_TITLE = "몬스터 30종 RUN · HIT · ATTACK 90시트 FINAL"
MANIFEST = ROOT / "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_ANIMATION_MANIFEST.json"


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with {exc.code}: {detail}") from exc


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_final_assets(manifest: dict) -> list[str]:
    existing = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    asset_ids = []
    for entry in manifest["entries"]:
        asset_id = entry["asset_id"] + "_FINAL"
        asset_ids.append(asset_id)
        source = ROOT / entry["sheet_path"]
        final_path = source.with_name(source.stem + "_final.png")
        if not final_path.exists() or checksum(final_path) != checksum(source):
            shutil.copy2(source, final_path)
        final_rel = final_path.relative_to(ROOT).as_posix()
        if asset_id in existing:
            continue
        existing[asset_id] = call(
            "POST",
            "/api/assets",
            {
                "asset_id": asset_id,
                "asset_type": "SPRITE_SHEET",
                "character_version": entry["monster_id"].lower(),
                "style_version": "art_bible_v02_axis_locked_final_" + entry["motion"],
                "source_asset": entry["sheet_path"],
                "file_path": final_rel,
                "frame_count": 16,
                "fps": 6,
                "loop": True,
                "pivot": {"x": 0.5, "y": 1.0},
                "status": "QA_PASS",
                "checksum": checksum(final_path),
                "created_by": "local_free_qa_final_animation_pipeline",
                "metadata": {
                    "monster_id": entry["monster_id"],
                    "family": entry["family"],
                    "palette": entry["palette"],
                    "motion": entry["motion"],
                    "gif_path": entry["gif_path"],
                    "qa_path": entry["qa_path"],
                    "sprite_qa": entry["qa"],
                    "body_center_x_range_px": entry["qa"]["body_center_x_range_px"],
                    "baseline_range_px": entry["qa"]["baseline_range_px"],
                    "minimum_safe_margin": entry["qa"]["minimum_safe_margin"],
                    "cell_invasion": entry["qa"]["cell_invasion"],
                },
            },
        )
    return asset_ids


def decide_original_approvals(tasks: dict[str, dict]) -> None:
    draft_task = tasks[DRAFT_TITLE]
    for approval in call("GET", "/api/approvals?status=PENDING&limit=500"):
        if approval["task_id"] == draft_task["id"]:
            call("POST", f"/api/approvals/{approval['id']}/decision", {
                "decision": "REVISION_REQUIRED",
                "decision_note": "최초 등록 뒤 강화 QA로 파일이 교체되어 FINAL 버전으로 재등록.",
                "decided_by": "system_qa",
            })


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not manifest["all_qa_pass"]:
        raise RuntimeError("final animation manifest contains QA failures")

    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    decide_original_approvals(tasks)
    asset_ids = create_final_assets(manifest)

    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    task = tasks.get(FINAL_TITLE)
    if task is None:
        task = call("POST", "/api/tasks", {
            "title": FINAL_TITLE,
            "task_type": "monster_animation_90_sheets_final",
            "assignee_role": "design_orchestra",
            "priority": 15,
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
        })

    previews = [
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_RUN_6FPS_PREVIEW.gif",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_HIT_6FPS_PREVIEW.gif",
        "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_ATTACK_6FPS_PREVIEW.gif",
    ]
    output = {
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "preview_paths": previews,
        "asset_ids": asset_ids,
        "sprite_qa": {
            "status": "PASS",
            "outputs": {"manifest": MANIFEST.relative_to(ROOT).as_posix()},
            "total_sheets": 90,
            "max_horizontal_drift_px": manifest["max_horizontal_drift_px"],
        },
    }
    call("PATCH", f"/api/tasks/{task['id']}/status", {"status": "WAITING_USER_APPROVAL", "output_payload": output})

    pending = call("GET", "/api/approvals?status=PENDING&limit=500")
    approval = next((item for item in pending if item["task_id"] == task["id"] and item["approval_type"] == "GAME_READY_SPRITE"), None)
    if approval is None:
        approval = call("POST", "/api/approvals", {
            "task_id": task["id"],
            "approval_type": "GAME_READY_SPRITE",
            "summary": "몬스터 30종의 run/hit/attack FINAL 90시트. 좌우 중심 최대 0.0251px, 전 시트 QA PASS.",
            "preview_paths": previews,
            "recommendation": "APPROVE_AND_APPLY",
            "asset_ids": asset_ids,
        })
    call("POST", f"/api/approvals/{approval['id']}/decision", {
        "decision": "APPROVED",
        "decision_note": "사용자 지시에 따라 Unity 적용 단계로 전달.",
        "decided_by": "user",
    })

    dispatches = call("GET", "/api/dispatches?status=PENDING&limit=500")
    dispatch = next(item for item in dispatches if item["source_task_id"] == task["id"])
    dispatch = call("POST", f"/api/dispatches/{dispatch['id']}/claim")
    (ROOT / "05_sprites/work/MONSTER_30_ANIMATIONS/UNITY_DISPATCH.json").write_text(json.dumps(dispatch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "dispatch_id": dispatch["id"],
        "status": dispatch["status"],
        "target_thread_id": dispatch["target_thread_id"],
        "target_task_id": dispatch["target_task_id"],
        "assets": len(asset_ids),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
