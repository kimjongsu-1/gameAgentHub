from typing import Any

from sqlalchemy.orm import Session

from app.handoff import build_handoff_package, find_worker
from app.models import Approval, Dispatch, Task


GAME_READY_APPROVAL_TYPES = {"SPRITE_GIF", "SPRITE_SHEET", "GAME_READY_SPRITE"}


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
            "rule": "승인된 에셋만 Unity에 적용하고 런타임 캡처와 QA 결과를 반환한다.",
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
