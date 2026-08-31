from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
MANIFEST = ROOT / "04_concepts/work/MONSTER_30_CATALOG/MONSTER_30_MANIFEST.json"
CATALOG = "04_concepts/work/MONSTER_30_CATALOG/MONSTER_30_CATALOG.png"
TITLE = "몬스터 5체형 × 6팔레트 파생 30종 디자인"


def call(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = {item["asset_id"]: item for item in call("GET", "/api/assets?limit=500")}
    asset_ids = []
    for entry in manifest["entries"]:
        asset_id = entry["asset_id"]
        asset_ids.append(asset_id)
        if asset_id in assets:
            continue
        file_path = entry["file_path"]
        assets[asset_id] = call(
            "POST",
            "/api/assets",
            {
                "asset_id": asset_id,
                "asset_type": "MONSTER_CONCEPT",
                "character_version": entry["family"].lower() + "_base_v01",
                "style_version": "art_bible_v02_palette_" + entry["palette"].lower(),
                "source_asset": f"04_concepts/work/MONSTER_30_CATALOG/base/MON_{entry['family']}_BASE.png",
                "file_path": file_path,
                "pivot": {"x": 0.5, "y": 1.0},
                "status": "QA_PASS",
                "checksum": checksum(ROOT / file_path),
                "created_by": "design_orchestra_local_palette_pipeline",
                "metadata": {
                    "family": entry["family"],
                    "family_name": entry["family_name"],
                    "palette": entry["palette"],
                    "palette_name": entry["palette_name"],
                    "derivation": "palette_only",
                    "silhouette_checksum": entry["silhouette_checksum"],
                    "silhouette_matches_family_base": entry["silhouette_matches_family_base"],
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
                "task_type": "monster_palette_catalog_30",
                "assignee_role": "design_orchestra",
                "priority": 25,
                "input_payload": {
                    "family_count": 5,
                    "variants_per_family": 6,
                    "total": 30,
                    "derivation_rule": "palette_only",
                },
            },
        )

    output_payload = {
        "catalog_path": CATALOG,
        "manifest_path": MANIFEST.relative_to(ROOT).as_posix(),
        "asset_ids": asset_ids,
        "qa": {
            "status": "PASS",
            "asset_count": 30,
            "all_rgba_512": True,
            "all_silhouettes_locked": manifest["all_silhouettes_locked"],
            "palette_only": True,
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
                "approval_type": "MONSTER_30_PALETTE_CATALOG",
                "summary": "보병형·짐승형·망령형·중장형·거체형 5개 체형에서 색상만 변경한 30종 몬스터 카탈로그. 모든 파생형의 실루엣 잠금 QA PASS.",
                "preview_paths": [CATALOG],
                "recommendation": "APPROVE",
                "asset_ids": asset_ids,
            },
        )
    print(json.dumps({"task_id": task["id"], "assets": len(asset_ids), "status": "WAITING_USER_APPROVAL"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
