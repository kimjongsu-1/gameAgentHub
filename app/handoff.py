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


DESIGN_PROFILES = {
    "entity_design": {
        "name": "캐릭터 · 몬스터 · NPC",
        "prompt_profile": "design_entity_v1",
        "required_outputs": [
            "투명 배경 원본 PNG와 정면 기준 이미지",
            "식별 요소·색상·비율을 기록한 디자인 명세",
            "애니메이션 작업이면 정확한 16프레임 4x4 시트와 중심축 정렬본",
            "에셋 manifest JSON",
        ],
        "requirements": [
            "캐릭터, 몬스터, NPC의 얼굴·체형·실루엣·의상·장비 식별 요소를 모든 결과에서 동일하게 유지한다.",
            "SD 2.5등신 비율과 모바일 축소 화면에서 읽히는 실루엣을 우선한다.",
            "애니메이션은 외곽 bbox만 맞추지 말고 머리·몸통·골반의 시각 중심과 전체 크기를 프레임마다 고정한다.",
            "대기/걷기 루프의 좌우·상하 중심 이동은 1px 이하, 의도하지 않은 크기 변화는 2% 이하로 제한한다.",
            "발바닥 기준선과 bottom-center pivot(x=0.5, y=1.0)을 유지한다.",
            "서로 다른 생성 후보를 한 애니메이션의 연속 프레임처럼 섞지 않는다.",
        ],
    },
    "world_item_design": {
        "name": "맵 · 배경화면 · 아이템",
        "prompt_profile": "design_world_item_v1",
        "required_outputs": [
            "맵 또는 배경 원본 PNG와 레이어 분리 명세",
            "아이템이면 투명 배경 원본과 128px·512px 판독성 확인본",
            "색상 팔레트·광원·원근·타일 연결 규칙",
            "에셋 manifest JSON",
        ],
        "requirements": [
            "게임 설정집의 시대·지역·영맥 분위기와 색상 팔레트를 유지한다.",
            "캐릭터 전투 영역과 UI 가독성을 방해하지 않도록 배경 대비와 시선 집중도를 조절한다.",
            "맵은 전경·중경·후경과 충돌/장식 레이어를 구분하고 반복 타일의 경계가 드러나지 않게 한다.",
            "배경화면은 화면 비율과 안전 영역을 명시하고 중요한 오브젝트가 UI 영역에 가려지지 않게 한다.",
            "아이템은 작은 크기에서도 종류와 희귀도가 구분되며 외곽 여백과 중심을 통일한다.",
            "이미지 안에 글자, 로고, 워터마크, 임의 UI를 넣지 않는다.",
        ],
    },
    "skill_vfx_design": {
        "name": "스킬 이펙트 · 스킬",
        "prompt_profile": "design_skill_vfx_v1",
        "required_outputs": [
            "스킬 기능 명세(범위·타이밍·피해 시점·속성)",
            "투명 배경 이펙트 프레임 시트와 6fps 미리보기 GIF",
            "anticipation·impact·recovery 프레임 구간표",
            "에셋 manifest JSON",
        ],
        "requirements": [
            "스킬의 범위, 방향, 발동 지점, 타격 시점이 모바일 화면에서 즉시 읽혀야 한다.",
            "anticipation, impact, recovery 단계를 명확히 분리하고 핵심 타격 프레임을 가장 강하게 표현한다.",
            "이펙트 중심축과 캔버스 중심을 고정하되 의도한 방향성 이동만 허용한다.",
            "투명 RGBA 배경을 사용하고 프레임 가장자리 잘림, 잔상 점프, 밝기 깜빡임을 방지한다.",
            "캐릭터 원본 디자인을 임의로 다시 그리거나 변경하지 않는다.",
            "과도한 광량과 불투명 연기로 캐릭터·몬스터·피격 지점을 가리지 않는다.",
        ],
    },
}


def design_profile_for_task(task: Task) -> tuple[str, dict[str, Any]]:
    task_type = task.task_type.lower()
    asset_kind = str((task.input_payload or {}).get("asset_kind", "")).lower()
    marker = f"{task_type} {asset_kind}"
    if any(value in marker for value in ("skill", "vfx", "effect")):
        profile_id = "skill_vfx_design"
    elif any(value in marker for value in ("map", "background", "environment", "item", "icon")):
        profile_id = "world_item_design"
    else:
        profile_id = "entity_design"
    return profile_id, DESIGN_PROFILES[profile_id]


def required_outputs_for(role: str, design_profile: dict[str, Any] | None = None) -> list[str]:
    if role == "design_orchestra" and design_profile:
        return design_profile["required_outputs"]
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
    profile_id = None
    design_profile = None
    if role == "design_orchestra":
        profile_id, design_profile = design_profile_for_task(task)
    required_outputs = required_outputs_for(role, design_profile)
    profile_requirements = design_profile["requirements"] if design_profile else []
    alignment_requirements = design_alignment_requirements() if role == "design_orchestra" and profile_id == "entity_design" else []
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
        "design_profile_id": profile_id,
        "design_profile_name": design_profile["name"] if design_profile else None,
        "prompt_profile": design_profile["prompt_profile"] if design_profile else None,
        "profile_requirements": profile_requirements,
        "alignment_requirements": alignment_requirements,
        "approval_policy": "결과물은 무료 로컬 QA와 사용자 승인을 통과하기 전에는 게임에 적용하지 않는다.",
        "created_at": created_at,
    }
    output_lines = [f"- {item}" for item in required_outputs]
    alignment_lines = [f"- {item}" for item in alignment_requirements]
    profile_lines = [f"- {item}" for item in profile_requirements]
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
        *( ["", f"전문 제작군: {design_profile['name']}", f"프롬프트 프로필: {design_profile['prompt_profile']}", *profile_lines] if design_profile else [] ),
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
        "design_profile_id": profile_id,
        "design_profile_name": design_profile["name"] if design_profile else None,
        "prompt_profile": design_profile["prompt_profile"] if design_profile else None,
        "markdown_path": markdown_path.relative_to(workspace_root).as_posix(),
        "json_path": json_path.relative_to(workspace_root).as_posix(),
        "prompt": prompt,
    }
