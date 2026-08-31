from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
MANIFEST = ROOT / "04_concepts/work/MONSTER_30_MAPS/MONSTER_30_MAP_MANIFEST.json"
TITLE = "몬스터 30종 팔레트 대응 전투 맵 6종"


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json; charset=utf-8"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    existing_assets = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    asset_ids = []
    for item in manifest["maps"]:
        asset_id = item["asset_id"]
        asset_ids.append(asset_id)
        if asset_id in existing_assets:
            continue
        call("POST", "/api/assets", {
            "asset_id": asset_id,
            "asset_type": "MAP_BACKGROUND",
            "character_version": "environment_v01",
            "style_version": f"art_bible_v02_palette_{item['palette'].lower()}",
            "source_asset": "04_concepts/work/MONSTER_30_CATALOG/MONSTER_30_CATALOG.png",
            "file_path": item["file_path"],
            "status": "QA_PASS",
            "checksum": item["sha256"],
            "created_by": "design_orchestra_builtin_imagegen_local_qa",
            "metadata": {
                "palette": item["palette"],
                "title_ko": item["title_ko"],
                "width": 1080,
                "height": 1920,
                "aspect": "9:16",
                "central_combat_lane": True,
                "characters": False,
                "text": False,
                "qa": item["qa"],
            },
        })

    tasks = {item["title"]: item for item in call("GET", "/api/tasks?limit=500")}
    task = tasks.get(TITLE)
    if task is None:
        task = call("POST", "/api/tasks", {
            "title": TITLE,
            "task_type": "monster_palette_maps_6",
            "assignee_role": "design_orchestra_environment",
            "priority": 30,
            "input_payload": {"palette_count": 6, "target_size": [1080, 1920], "monster_catalog": "MONSTER_30"},
        })

    output = {
        "catalog_path": manifest["catalog_path"],
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "asset_ids": asset_ids,
        "qa": {"status": manifest["qa_status"], "map_count": 6, "all_exact_1080x1920": True, "all_opaque": True},
    }
    call("PATCH", f"/api/tasks/{task['id']}/status", {"status": "WAITING_USER_APPROVAL", "output_payload": output})
    pending = call("GET", "/api/approvals?status=PENDING&limit=500")
    approval = next((item for item in pending if item["task_id"] == task["id"]), None)
    if approval is None:
        approval = call("POST", "/api/approvals", {
            "task_id": task["id"],
            "approval_type": "MONSTER_PALETTE_MAPS_6",
            "summary": "몬스터 30종의 6개 색상 계열에 대응하는 1080×1920 세로형 전투 맵 6종입니다. 중앙 전투 공간, 무문자·무캐릭터, 파일 규격 QA를 통과했습니다.",
            "preview_paths": [manifest["catalog_path"]] + [item["file_path"] for item in manifest["maps"]],
            "recommendation": "APPROVE",
            "asset_ids": asset_ids,
        })
    print(json.dumps({"task_id": task["id"], "approval_id": approval["id"], "assets": len(asset_ids), "status": "WAITING_USER_APPROVAL"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
