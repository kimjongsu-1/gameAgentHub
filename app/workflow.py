import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.handoff import build_handoff_package, find_worker
from app.models import Approval, Asset, Dispatch, Task
from app.unity_bridge import UnityImportConfig, stage_unity_import


GAME_READY_APPROVAL_TYPES = {"SPRITE_GIF", "SPRITE_SHEET", "GAME_READY_SPRITE"}


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def promote_approved_assets(db: Session, approval: Approval, workspace_root: Path) -> list[Asset]:
    promoted = []
    for link in approval.linked_assets:
        asset = db.query(Asset).filter(Asset.asset_id == link.asset_id).one()
        source = (workspace_root / asset.file_path).resolve()
        if not source.is_relative_to(workspace_root) or not source.is_file():
            raise ValueError(f"Approved asset source is invalid: {asset.file_path}")
        if file_checksum(source) != asset.checksum:
            raise ValueError(f"Approved asset checksum changed: {asset.asset_id}")
        destination = (workspace_root / "05_sprites" / "approved" / source.name).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and file_checksum(destination) != asset.checksum:
            raise ValueError(f"Approved destination already contains different data: {destination.name}")
        if not destination.exists():
            shutil.copy2(source, destination)

        asset.file_path = destination.relative_to(workspace_root).as_posix()
        asset.status = "APPROVED"
        asset.approved_by = approval.decided_by

        manifest_path = write_asset_manifest(asset, workspace_root)
        qa_result_path = write_asset_qa_result(asset, workspace_root)
        staging_receipt = stage_unity_package(asset, manifest_path, qa_result_path, workspace_root)
        asset.asset_metadata = {
            **(asset.asset_metadata or {}),
            "manifest_path": manifest_path.relative_to(workspace_root).as_posix(),
            "qa_result_path": qa_result_path.relative_to(workspace_root).as_posix(),
            "unity_staging": staging_receipt,
        }
        promoted.append(asset)
    return promoted


def write_asset_manifest(asset: Asset, workspace_root: Path) -> Path:
    manifest_dir = workspace_root / "05_sprites" / "approved" / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{asset.asset_id}.json"
    payload = {
        "schema_version": 1,
        "asset_id": asset.asset_id,
        "asset_type": asset.asset_type,
        "status": asset.status,
        "file_path": asset.file_path,
        "checksum": asset.checksum,
        "frame_count": asset.frame_count,
        "fps": asset.fps,
        "loop": asset.loop,
        "pivot": asset.pivot,
        "character_version": asset.character_version,
        "style_version": asset.style_version,
        "metadata": asset.asset_metadata or {},
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def write_asset_qa_result(asset: Asset, workspace_root: Path) -> Path:
    qa_result = (asset.asset_metadata or {}).get("sprite_qa") or {"status": "PASS"}
    qa_dir = workspace_root / "05_sprites" / "approved" / "qa_results"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / f"{asset.asset_id}.json"
    qa_payload = {**qa_result, "status": qa_result.get("status", "PASS"), "asset_id": asset.asset_id}
    qa_path.write_text(json.dumps(qa_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return qa_path


def unity_resource_name(asset_id: str) -> str:
    parts = [part for part in asset_id.lower().replace("-", "_").split("_") if part]
    name = "".join(part.capitalize() for part in parts) or "ApprovedSprite"
    if not name[0].isalpha():
        name = f"Sprite{name}"
    return name


def stage_unity_package(asset: Asset, manifest_path: Path, qa_result_path: Path, workspace_root: Path) -> dict[str, Any]:
    output_root = workspace_root / "06_game" / "approved_imports"
    package_dir = output_root / asset.asset_id
    if package_dir.exists():
        return {
            "asset_id": asset.asset_id,
            "package_dir": package_dir.relative_to(workspace_root).as_posix(),
            "request_path": (package_dir / "request.json").relative_to(workspace_root).as_posix(),
            "status": "EXISTS",
        }
    receipt = stage_unity_import(
        manifest_path,
        qa_result_path,
        output_root,
        UnityImportConfig(
            resource_name=unity_resource_name(asset.asset_id),
            frame_count=asset.frame_count or 16,
            fps=asset.fps or 12,
            loop=True if asset.loop is None else asset.loop,
            pivot_x=(asset.pivot or {}).get("x", 0.5),
            pivot_y=(asset.pivot or {}).get("y", 0.05),
        ),
    )
    return {
        **receipt,
        "package_dir": Path(receipt["package_dir"]).relative_to(workspace_root).as_posix(),
        "request_path": Path(receipt["request_path"]).relative_to(workspace_root).as_posix(),
        "source_path": Path(receipt["source_path"]).relative_to(workspace_root).as_posix(),
        "status": "STAGED",
    }


def queue_game_dispatch(
    db: Session,
    source_task: Task,
    approval: Approval,
    agent_config: dict[str, Any],
    workspace_root,
) -> Dispatch | None:
    qa_result = (source_task.output_payload or {}).get("sprite_qa")
    if approval.approval_type not in GAME_READY_APPROVAL_TYPES:
        return None
    if not qa_result or qa_result.get("status") != "PASS":
        return None

    worker = find_worker(agent_config, "game_development")
    integration_task = Task(
        title=f"[게임 적용] {source_task.title}",
        task_type="unity_integration",
        assignee_role="game_development",
        assignee_thread_id=worker["thread_id"],
        status="READY",
        priority=source_task.priority,
        input_payload={
            "source_task_id": source_task.id,
            "approval_id": approval.id,
            "approved_by": approval.decided_by,
            "qa_status": qa_result["status"],
            "qa_outputs": qa_result.get("outputs", {}),
            "preview_paths": approval.preview_paths,
            "approved_assets": [
                {
                    "asset_id": link.asset_id,
                    "file_path": link.asset.file_path,
                    "manifest_path": (link.asset.asset_metadata or {}).get("manifest_path"),
                    "qa_result_path": (link.asset.asset_metadata or {}).get("qa_result_path"),
                    "unity_staging": (link.asset.asset_metadata or {}).get("unity_staging"),
                }
                for link in approval.linked_assets
            ],
            "rule": "승인된 에셋만 Unity에 적용하고 런타임 캡처와 QA 결과를 허브로 반환한다.",
        },
    )
    db.add(integration_task)
    db.flush()
    package = build_handoff_package(integration_task, worker, workspace_root)
    integration_task.output_payload = {"handoff_package": package}
    dispatch = Dispatch(
        source_task_id=source_task.id,
        target_task_id=integration_task.id,
        approval_id=approval.id,
        target_role=worker["role"],
        target_thread_id=worker["thread_id"],
        target_thread_title=worker["thread_title"],
        prompt=package["prompt"],
        dispatch_payload=package,
    )
    db.add(dispatch)
    return dispatch
