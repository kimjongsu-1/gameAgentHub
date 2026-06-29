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


def required_outputs_for(role: str) -> list[str]:
    if role == "design_orchestra":
        return [
            "원본 PNG",
            "정확한 16프레임 4x4 스프라이트 시트",
            "프레임별 캐릭터 발 기준점과 몸 중심이 흔들리지 않는 정렬본",
            "에셋 manifest JSON",
        ]
    return ["Unity 적용 보고서", "런타임 캡처", "빌드 및 테스트 보고서"]


def design_alignment_requirements() -> list[str]:
    return [
        "모든 프레임은 같은 캔버스 크기와 같은 4x4 셀 크기를 사용한다.",
        "캐릭터의 발바닥 기준점은 모든 프레임에서 같은 y좌표에 있어야 한다.",
        "제자리 동작/걷기 루프의 몸 중심 x좌표는 의도한 이동이 아닌 이상 거의 고정한다.",
        "프레임마다 캐릭터 전체가 위아래/좌우로 떠다니듯 이동하면 안 된다.",
        "무기, 머리, 팔, 이펙트는 움직여도 되지만 몸통 기준 위치는 안정적으로 유지한다.",
        "게임 적용 pivot은 기본적으로 bottom-center, 즉 x=0.5, y=1.0 기준으로 맞춘다.",
        "로컬 QA가 pivot_delta와 PIVOT_JITTER를 검사하므로, 프레임별 bbox center/bottom 변화가 작아야 한다.",
    ]


def closing_lines_for(role: str) -> list[str]:
    if role == "design_orchestra":
        return [
            "완성 결과물을 게임에 직접 적용하지 말고 통합 허브로 반환하세요.",
            "무료 로컬 QA와 사용자 최종 승인을 통과한 에셋만 게임개발 채팅으로 전달됩니다.",
            "기획과 자료조사는 사용자가 직접 제공한 입력 명세를 기준으로만 해석하세요.",
            "프레임 위치가 흔들리면 재작업 대상입니다. 반드시 발 기준점과 몸 중심을 맞춘 뒤 제출하세요.",
        ]
    return [
        "승인된 입력 에셋만 사용하세요.",
        "런타임 결과와 발견한 문제를 통합 허브로 반환하세요.",
        "사용자가 게임개발 시작을 허가한 뒤에만 진행하세요.",
    ]


def build_handoff_package(task: Task, worker: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    role = worker["role"]
    required_outputs = required_outputs_for(role)
    alignment_requirements = design_alignment_requirements() if role == "design_orchestra" else []
    payload = {
        "schema_version": 2,
        "task_id": task.id,
        "title": task.title,
        "task_type": task.task_type,
        "target_role": role,
        "target_thread_id": worker["thread_id"],
        "target_thread_title": worker["thread_title"],
        "input_payload": task.input_payload,
        "planning_mode": "user_direct",
        "repeated_qa_mode": "free_local_tools",
        "required_outputs": required_outputs,
        "alignment_requirements": alignment_requirements,
        "approval_policy": "결과물은 무료 로컬 QA와 사용자 승인을 통과하기 전에는 게임에 적용하지 않는다.",
        "created_at": created_at,
    }
    output_lines = [f"- {item}" for item in required_outputs]
    alignment_lines = [f"- {item}" for item in alignment_requirements]
    closing_lines = closing_lines_for(role)
    prompt_parts = [
        f"[통합 제작 허브 작업 {task.id}]",
        f"작업명: {task.title}",
        f"작업 유형: {task.task_type}",
        "",
        "입력 명세:",
        json.dumps(task.input_payload, ensure_ascii=False, indent=2),
        "",
        "운영 원칙:",
        "- 기획/자료조사는 사용자가 직접 제공한 내용을 기준으로 한다.",
        "- 반복 검사는 무료 로컬 QA를 우선 사용한다.",
        "- 외부 AI API를 자동 호출하지 않는다.",
        "",
        "필수 결과물:",
        *output_lines,
    ]
    if alignment_lines:
        prompt_parts.extend(
            [
                "",
                "16프레임 정렬/흔들림 방지 필수 조건:",
                *alignment_lines,
            ]
        )
    prompt_parts.extend(["", *closing_lines])
    prompt = "\n".join(prompt_parts)
    payload["prompt"] = prompt
    outbox = workspace_root / "00_control" / "pipeline" / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    json_path = outbox / f"{task.id}.json"
    markdown_path = outbox / f"{task.id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(f"# {task.title}\n\n{prompt}\n", encoding="utf-8")
    return {
        "task_id": task.id,
        "target_role": role,
        "target_thread_id": worker["thread_id"],
        "target_thread_title": worker["thread_title"],
        "markdown_path": markdown_path.relative_to(workspace_root).as_posix(),
        "json_path": json_path.relative_to(workspace_root).as_posix(),
        "prompt": prompt,
    }
