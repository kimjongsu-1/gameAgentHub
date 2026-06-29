import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import Task


def find_worker(agent_config: dict[str, Any], role: str) -> dict[str, Any]:
    for worker in agent_config["workers"]:
        if worker["role"] == role:
            return worker
    raise ValueError(f"No worker configured for role: {role}")


def build_handoff_package(task: Task, worker: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    is_design = worker["role"] == "design_orchestra"
    required_outputs = (
        ["원본 PNG", "정확히 16프레임인 스프라이트 시트", "에셋 manifest JSON"]
        if is_design
        else ["Unity 적용 보고서", "런타임 캡처", "빌드 및 테스트 보고서"]
    )
    payload = {
        "schema_version": 1,
        "task_id": task.id,
        "title": task.title,
        "task_type": task.task_type,
        "target_role": worker["role"],
        "target_thread_id": worker["thread_id"],
        "target_thread_title": worker["thread_title"],
        "input_payload": task.input_payload,
        "required_outputs": required_outputs,
        "approval_policy": "결과는 중앙 QA와 사용자 승인을 통과하기 전 게임에 적용하지 않는다.",
        "created_at": created_at,
    }
    output_lines = [f"- {item}" for item in required_outputs]
    closing_lines = (
        [
            "완성 결과는 게임에 직접 적용하지 말고 오케스트레이터에 반환하세요.",
            "중앙 QA와 사용자 최종 승인을 통과한 에셋만 게임개발 채팅으로 전달합니다.",
        ]
        if is_design
        else [
            "승인된 입력 에셋만 사용하세요.",
            "런타임 결과와 발견한 문제를 오케스트레이터에 반환하세요.",
        ]
    )
    prompt = "\n".join(
        [
            f"[통합 제작 허브 작업 {task.id}]",
            f"작업명: {task.title}",
            f"작업 유형: {task.task_type}",
            "",
            "입력 명세:",
            json.dumps(task.input_payload, ensure_ascii=False, indent=2),
            "",
            "필수 결과물:",
            *output_lines,
            "",
            *closing_lines,
        ]
    )
    payload["prompt"] = prompt
    outbox = workspace_root / "00_control" / "pipeline" / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    json_path = outbox / f"{task.id}.json"
    markdown_path = outbox / f"{task.id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(f"# {task.title}\n\n{prompt}\n", encoding="utf-8")
    return {
        "task_id": task.id,
        "target_role": worker["role"],
        "target_thread_id": worker["thread_id"],
        "target_thread_title": worker["thread_title"],
        "markdown_path": markdown_path.relative_to(workspace_root).as_posix(),
        "json_path": json_path.relative_to(workspace_root).as_posix(),
        "prompt": prompt,
    }
