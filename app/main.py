import json
from io import BytesIO
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.handoff import build_handoff_package, find_worker
from app.models import (
    ApiUsage,
    Approval,
    ApprovalAsset,
    Asset,
    Dispatch,
    RuntimeReport,
    SuperGrokPromptPackage,
    Task,
)
from app.schemas import (
    TASK_STATUSES,
    ApiUsageCreate,
    ApiUsageRead,
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    AssetCreate,
    AssetRead,
    DispatchRead,
    DispatchStatusUpdate,
    HandoffPackageRead,
    RuntimeReportCreate,
    RuntimeReportRead,
    SpriteQARunRequest,
    SuperGrokPromptCreate,
    SuperGrokPromptRead,
    TaskCreate,
    TaskRead,
    TaskStatusUpdate,
)
from app.sprite_qa import QAConfig, SpriteQAError, run_sprite_qa
from app.workflow import promote_approved_assets, queue_game_dispatch


settings = get_settings()
static_dir = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url.startswith("sqlite"):
        Path(settings.database_url.removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


def load_agents() -> dict:
    path = settings.project_root / "config" / "agents.json"
    return json.loads(path.read_text(encoding="utf-8"))


def worker_is_configured(worker: dict) -> bool:
    thread_id = str(worker.get("thread_id") or "")
    return bool(thread_id and not thread_id.startswith("TODO_"))


def _legacy_pipeline_stage_status(db: Session) -> list[dict]:
    agents = load_agents()
    role_names = ["user_direct_planning", "design_orchestra", "game_development"]
    stages = []
    for role in role_names:
        worker = next((item for item in agents["workers"] if item["role"] == role), None)
        role_tasks = list(db.scalars(select(Task).where(Task.assignee_role == role)))
        counts = Counter(task.status for task in role_tasks)
        stages.append(
            {
                "role": role,
                "thread_title": worker["thread_title"] if worker else role,
                "thread_id": worker["thread_id"] if worker else None,
                "configured": worker_is_configured(worker) if worker else False,
                "task_counts": counts,
                "paused": bool(counts.get("PAUSED", 0)),
                "active": bool(counts.get("RUNNING", 0)),
            }
        )
    return stages


def _legacy_pipeline_architecture_status(db: Session) -> dict:
    stages = pipeline_stage_status(db)
    planning_stage = None
    game_stage = next((stage for stage in stages if stage["role"] == "game_development"), None)
    return {
        "pm_owner": "MCP server: game_production_pm",
        "hub_role": "FastAPI dashboard, DB, approval, QA, dispatch queue, runtime report storage",
        "routing_model": "MCP PM creates/updates tasks and dispatch records; Codex dispatcher sends approved dispatch prompts to existing worker chats.",
        "dispatcher_mode": "manual",
        "dispatcher_status": "disabled_until_user_requests",
        "external_ai_policy": settings.gateway_default_policy,
        "external_ai_calls_enabled": settings.external_ai_calls_enabled,
        "game_development_locked": bool(game_stage and game_stage["paused"]),
        "planning_connected": bool(planning_stage and planning_stage["configured"]),
        "next_required_connections": [
            {
                "role": "user_direct_planning",
                "needed": not bool(planning_stage and planning_stage["configured"]),
                "action": "기획/자료조사는 사용자가 직접 수행하므로 별도 thread_id 등록이 필요하지 않음",
            },
            {
                "role": "dispatcher",
                "needed": True,
                "action": "사용자가 원할 때만 수동 dispatch 처리 또는 자동화 재활성화",
            },
        ],
        "flow": [
            {"step": 1, "owner": "MCP PM", "action": "작업 생성/상태 조회/중지·재개 제어"},
            {"step": 2, "owner": "FastAPI Hub", "action": "DB 저장, 승인/QA/dispatch 큐 관리"},
            {"step": 3, "owner": "Codex Dispatcher", "action": "승인된 dispatch를 기존 채팅창으로 전달"},
            {"step": 4, "owner": "Worker Chat", "action": "기획/디자인/개발 작업 수행"},
            {"step": 5, "owner": "FastAPI Hub", "action": "결과 보고서와 승인 상태 회수"},
        ],
    }


def pipeline_stage_status(db: Session) -> list[dict]:
    agents = load_agents()
    stages = [
        {
            "role": "user_direct_planning",
            "thread_title": "사용자 직접 기획",
            "thread_id": None,
            "configured": True,
            "task_counts": {},
            "paused": False,
            "active": False,
            "mode": agents.get("planning", {}).get("mode", "user_direct"),
            "description": agents.get("planning", {}).get(
                "description",
                "기획과 자료조사는 사용자가 직접 수행하고 PM이 작업 지시서로 정리한다.",
            ),
        }
    ]
    for role in ["design_orchestra", "local_free_qa", "game_development"]:
        if role == "local_free_qa":
            qa_tasks = list(db.scalars(select(Task).where(Task.status.in_(["QA_RUNNING", "REVISION_REQUIRED"]))))
            counts = Counter(task.status for task in qa_tasks)
            stages.append(
                {
                    "role": role,
                    "thread_title": "무료 로컬 반복 QA",
                    "thread_id": None,
                    "configured": True,
                    "task_counts": counts,
                    "paused": False,
                    "active": bool(counts.get("QA_RUNNING", 0)),
                    "mode": agents.get("qa", {}).get("mode", "free_local_tools"),
                    "description": agents.get("qa", {}).get(
                        "description",
                        "외부 AI API 없이 로컬 Sprite QA와 런타임 보고서 등록으로 반복 검사를 처리한다.",
                    ),
                }
            )
            continue
        worker = next((item for item in agents["workers"] if item["role"] == role), None)
        role_tasks = list(db.scalars(select(Task).where(Task.assignee_role == role)))
        counts = Counter(task.status for task in role_tasks)
        stages.append(
            {
                "role": role,
                "thread_title": worker["thread_title"] if worker else role,
                "thread_id": worker["thread_id"] if worker else None,
                "configured": worker_is_configured(worker) if worker else False,
                "task_counts": counts,
                "paused": bool(counts.get("PAUSED", 0)),
                "active": bool(counts.get("RUNNING", 0)),
            }
        )
    return stages


def pipeline_architecture_status(db: Session) -> dict:
    agents = load_agents()
    stages = pipeline_stage_status(db)
    game_stage = next((stage for stage in stages if stage["role"] == "game_development"), None)
    return {
        "pm_owner": "MCP server: game_production_pm",
        "hub_role": "FastAPI dashboard, DB, approval, local QA, dispatch queue, runtime report storage",
        "routing_model": "MCP PM creates/updates tasks and dispatch records; Codex dispatcher sends approved dispatch prompts to existing worker chats.",
        "planning_mode": agents.get("planning", {}).get("mode", "user_direct"),
        "planning_owner": agents.get("planning", {}).get("owner", "user"),
        "repeated_qa_mode": agents.get("qa", {}).get("mode", "free_local_tools"),
        "repeated_qa_owner": agents.get("qa", {}).get("owner", "local_hub"),
        "dispatcher_mode": "manual",
        "dispatcher_status": "disabled_until_user_requests",
        "external_ai_policy": settings.gateway_default_policy,
        "external_ai_calls_enabled": settings.external_ai_calls_enabled,
        "game_development_locked": bool(game_stage and game_stage["paused"]),
        "planning_connected": True,
        "next_required_connections": [
            {
                "role": "dispatcher",
                "needed": True,
                "action": "사용자가 명시적으로 요청할 때만 수동 dispatch 처리 또는 자동화 재활성화",
            },
        ],
        "flow": [
            {"step": 1, "owner": "User", "action": "기획과 자료조사를 직접 작성"},
            {"step": 2, "owner": "MCP PM", "action": "사용자 기획을 작업 지시서로 정리하고 디자인 작업 생성"},
            {"step": 3, "owner": "Design Orchestra", "action": "캐릭터 디자인, 16프레임 스프라이트, 애니메이션 소스 제작"},
            {"step": 4, "owner": "Local Free QA", "action": "Sprite QA, GIF, 컨택트시트, 어니언스킨, 런타임 보고서로 반복 검사"},
            {"step": 5, "owner": "User", "action": "미적/게임성 최종 승인"},
            {"step": 6, "owner": "Game Development", "action": "사용자가 게임개발 시작을 허가한 뒤 승인 에셋만 Unity에 적용"},
        ],
    }


def resolve_workspace_path(value: str) -> Path:
    root = settings.resolved_workspace_root
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(400, detail="Path must stay inside the workspace")
    return resolved


def asset_to_schema(asset: Asset) -> AssetRead:
    return AssetRead(
        id=asset.id,
        asset_id=asset.asset_id,
        asset_type=asset.asset_type,
        character_version=asset.character_version,
        style_version=asset.style_version,
        source_asset=asset.source_asset,
        file_path=asset.file_path,
        frame_count=asset.frame_count,
        fps=asset.fps,
        loop=asset.loop,
        pivot=asset.pivot,
        status=asset.status,
        checksum=asset.checksum,
        created_by=asset.created_by,
        approved_by=asset.approved_by,
        metadata=asset.asset_metadata,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def build_super_grok_prompt(payload: SuperGrokPromptCreate, reference_image_path: str) -> tuple[str, str, dict]:
    character = payload.character_name or payload.asset_id or "attached character"
    request_label = "skill animation" if payload.request_type == "skill_animation" else "cinematic cutscene"
    style_notes = payload.style_notes or "Preserve the original character silhouette, outfit, color palette, and game-ready readability."
    prompt = "\n".join(
        [
            f"Use the attached single reference image as the exact character identity for a {request_label}.",
            f"Character: {character}",
            f"Goal: {payload.animation_goal}",
            f"Duration: about {payload.duration_seconds:g} seconds",
            f"Aspect ratio: {payload.aspect_ratio}",
            "",
            "Production requirements:",
            "- Keep the character recognizable from the source image.",
            "- Maintain consistent face, costume, proportions, weapon/accessory details, and color palette.",
            "- Create clear motion staging suitable for a mobile idle RPG.",
            "- Emphasize readable silhouettes, snappy timing, and strong anticipation/impact/recovery beats.",
            "- Avoid changing the character design unless explicitly required by the animation goal.",
            "",
            f"Style notes: {style_notes}",
            "",
            "Output focus:",
            "- A polished animation/cutscene preview that can be reviewed by the PM before game integration.",
            "- If the tool supports it, keep the background simple or transparent-friendly for later editing.",
        ]
    )
    negative_prompt = (
        "Do not redesign the character, do not change the costume, do not add extra limbs, "
        "do not create a different face, do not use unreadable motion blur, do not add text, "
        "logos, watermarks, UI frames, or unrelated background characters."
    )
    package_payload = payload.model_dump()
    package_payload.update(
        {
            "provider_target": "super_grok_manual",
            "external_api_call": False,
            "reference_image_path": reference_image_path,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "manual_steps": [
                "Open SuperGrok manually.",
                "Upload the reference image shown on the dashboard.",
                "Paste the generated prompt.",
                "Paste the negative prompt if the tool provides a negative prompt field.",
                "Return the result/capture to the hub for PM review.",
            ],
        }
    )
    return prompt, negative_prompt, package_payload


def safe_upload_name(filename: str) -> str:
    stem = Path(filename or "reference").stem or "reference"
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem).strip("_")
    return safe_stem[:80] or "reference"


def validate_uploaded_image(data: bytes, suffix: str) -> None:
    if not data:
        raise HTTPException(422, detail="Uploaded image is empty")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, detail="Uploaded image is larger than 15 MB")
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(422, detail="Only PNG, JPG, JPEG, or WebP reference images are supported")
    try:
        Image.open(BytesIO(data)).verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise HTTPException(422, detail="Uploaded file is not a valid image") from exc


def build_character_consistency_payload(
    character_name: str,
    reference_image_path: str,
    notes: str,
    variants: int,
) -> dict:
    return {
        "reference_image_path": reference_image_path,
        "character_name": character_name,
        "user_notes": notes,
        "requested_variants": variants,
        "test_goal": "참조 일러스트 1장을 기준으로 캐릭터 정체성이 통일되게 유지되는지 확인한다.",
        "consistency_requirements": [
            "얼굴 비율, 눈매, 표정 인상 유지",
            "체형, 키, 실루엣 유지",
            "의상 구조, 장식, 색상 팔레트 유지",
            "무기/소품의 형태와 위치 유지",
            "머리카락/뿔/꼬리/문양 같은 식별 요소 유지",
            "다른 캐릭터처럼 보이는 재해석 금지",
            "16프레임 제작 시 발 기준점과 몸 중심 정렬 유지",
        ],
        "requested_outputs": [
            "참조 일러스트와 같은 캐릭터로 보이는 테스트 이미지 또는 시트",
            "통일성 유지 체크리스트",
            "바뀐 부분이 있다면 수정 필요 항목",
        ],
    }


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/workspace-files/{file_path:path}", include_in_schema=False)
def workspace_file(file_path: str) -> FileResponse:
    path = resolve_workspace_path(file_path)
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    if path.suffix.lower() not in allowed or not path.is_file():
        raise HTTPException(404, detail="Preview not found")
    return FileResponse(path)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    return {"status": "ok", "environment": settings.app_env}


@app.get("/api/agents")
def agents() -> dict:
    return load_agents()


@app.get("/api/tasks", response_model=list[TaskRead])
def list_tasks(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Task]:
    query = select(Task).order_by(Task.priority, Task.created_at.desc()).limit(limit)
    if status:
        query = query.where(Task.status == status)
    return list(db.scalars(query))


@app.post("/api/tasks", response_model=TaskRead, status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    task = Task(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.patch("/api/tasks/{task_id}/status", response_model=TaskRead)
def update_task_status(task_id: str, payload: TaskStatusUpdate, db: Session = Depends(get_db)) -> Task:
    if payload.status not in TASK_STATUSES:
        raise HTTPException(422, detail=f"Unsupported status: {payload.status}")
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, detail="Task not found")
    task.status = payload.status
    if payload.output_payload is not None:
        task.output_payload = payload.output_payload
    task.resume_at = payload.resume_at
    db.commit()
    db.refresh(task)
    return task


@app.post("/api/design/character-consistency-tests", status_code=201)
async def create_character_consistency_test(
    file: UploadFile = File(...),
    character_name: str = Form(default="uploaded_character"),
    notes: str = Form(default=""),
    variants: int = Form(default=4),
    db: Session = Depends(get_db),
) -> dict:
    if variants < 1 or variants > 8:
        raise HTTPException(422, detail="variants must be between 1 and 8")

    suffix = Path(file.filename or "").suffix.lower()
    data = await file.read()
    validate_uploaded_image(data, suffix)

    upload_dir = settings.resolved_workspace_root / "03_character_masters" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{uuid4()}_{safe_upload_name(file.filename or 'reference')}{suffix}"
    upload_path.write_bytes(data)
    relative_reference = upload_path.relative_to(settings.resolved_workspace_root).as_posix()

    try:
        worker = find_worker(load_agents(), "design_orchestra")
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if not worker_is_configured(worker):
        raise HTTPException(422, detail="Worker thread is not configured for role: design_orchestra")

    payload = build_character_consistency_payload(character_name, relative_reference, notes, variants)
    task = Task(
        title=f"{character_name} 캐릭터 통일성 테스트",
        task_type="character_consistency_test",
        assignee_role="design_orchestra",
        priority=40,
        input_payload=payload,
    )
    db.add(task)
    db.flush()

    package = build_handoff_package(task, worker, settings.resolved_workspace_root)
    task.status = "READY"
    task.output_payload = {**(task.output_payload or {}), "handoff_package": package}
    dispatch = Dispatch(
        source_task_id=task.id,
        target_task_id=task.id,
        approval_id=None,
        target_role=worker["role"],
        target_thread_id=worker["thread_id"],
        target_thread_title=worker["thread_title"],
        prompt=package["prompt"],
        dispatch_payload=package,
    )
    db.add(dispatch)
    db.commit()
    db.refresh(task)
    db.refresh(dispatch)
    return {
        "reference_image_path": relative_reference,
        "task": TaskRead.model_validate(task).model_dump(mode="json"),
        "dispatch": DispatchRead.model_validate(dispatch).model_dump(mode="json"),
        "handoff_package": package,
    }


@app.post("/api/tasks/{task_id}/handoff-package", response_model=HandoffPackageRead)
def create_handoff_package(task_id: str, db: Session = Depends(get_db)) -> dict:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, detail="Task not found")
    try:
        worker = find_worker(load_agents(), task.assignee_role)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    package = build_handoff_package(task, worker, settings.resolved_workspace_root)
    task.status = "READY"
    task.output_payload = {**(task.output_payload or {}), "handoff_package": package}
    db.commit()
    return package


@app.post("/api/tasks/{task_id}/queue-dispatch", response_model=DispatchRead, status_code=201)
def queue_task_dispatch(task_id: str, db: Session = Depends(get_db)) -> Dispatch:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, detail="Task not found")
    if task.assignee_role == "game_development":
        approved_input = bool(task.input_payload.get("approval_id") and task.input_payload.get("source_task_id"))
        infrastructure_task = task.task_type in {"unity_bridge_setup", "pipeline_maintenance"}
        if not approved_input and not infrastructure_task:
            raise HTTPException(422, detail="Game dispatch requires an approved asset or infrastructure task")
    existing = db.scalar(
        select(Dispatch).where(
            Dispatch.target_task_id == task.id,
            Dispatch.status.in_(["PENDING", "CLAIMED", "SENT"]),
        )
    )
    if existing:
        raise HTTPException(409, detail=f"Task already has a {existing.status} dispatch")
    try:
        worker = find_worker(load_agents(), task.assignee_role)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if not worker_is_configured(worker):
        raise HTTPException(422, detail=f"Worker thread is not configured for role: {task.assignee_role}")
    package = build_handoff_package(task, worker, settings.resolved_workspace_root)
    task.status = "READY"
    task.output_payload = {**(task.output_payload or {}), "handoff_package": package}
    dispatch = Dispatch(
        source_task_id=task.input_payload.get("source_task_id", task.id),
        target_task_id=task.id,
        approval_id=task.input_payload.get("approval_id"),
        target_role=worker["role"],
        target_thread_id=worker["thread_id"],
        target_thread_title=worker["thread_title"],
        prompt=package["prompt"],
        dispatch_payload=package,
    )
    db.add(dispatch)
    db.commit()
    db.refresh(dispatch)
    return dispatch


@app.post("/api/sprite-qa/run")
def run_qa(payload: SpriteQARunRequest, db: Session = Depends(get_db)) -> dict:
    source = resolve_workspace_path(payload.source_path)
    output_value = payload.output_dir or f"05_sprites/qa/{source.stem}"
    output_dir = resolve_workspace_path(output_value)
    config = QAConfig(
        columns=payload.columns,
        rows=payload.rows,
        expected_frames=payload.expected_frames,
        fps=payload.fps,
        loop=payload.loop,
        chroma_key=payload.chroma_key,
        chroma_tolerance=payload.chroma_tolerance,
    )
    try:
        result = run_sprite_qa(source, output_dir, config)
    except SpriteQAError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    relative_outputs = {
        name: Path(path).relative_to(settings.resolved_workspace_root).as_posix()
        for name, path in result["outputs"].items()
    }
    result["source_path"] = source.relative_to(settings.resolved_workspace_root).as_posix()
    result["output_dir"] = output_dir.relative_to(settings.resolved_workspace_root).as_posix()
    result["outputs"] = relative_outputs

    mapped_status = "QA_PASS" if result["status"] == "PASS" else "REVISION_REQUIRED"
    if payload.task_id:
        task = db.get(Task, payload.task_id)
        if not task:
            raise HTTPException(404, detail="Task not found")
        task.status = "WAITING_USER_APPROVAL" if result["status"] == "PASS" else "REVISION_REQUIRED"
        task.output_payload = {**(task.output_payload or {}), "sprite_qa": result}
    if payload.asset_id:
        asset = db.scalar(select(Asset).where(Asset.asset_id == payload.asset_id))
        if not asset:
            raise HTTPException(404, detail="Asset not found")
        asset.status = mapped_status
        asset.asset_metadata = {**asset.asset_metadata, "sprite_qa": result}
    db.commit()
    return result


@app.get("/api/assets", response_model=list[AssetRead])
def list_assets(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AssetRead]:
    query = select(Asset).order_by(Asset.created_at.desc()).limit(limit)
    if status:
        query = query.where(Asset.status == status)
    return [asset_to_schema(asset) for asset in db.scalars(query)]


@app.post("/api/assets", response_model=AssetRead, status_code=201)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)) -> AssetRead:
    values = payload.model_dump(exclude={"metadata"})
    asset = Asset(**values, asset_metadata=payload.metadata)
    db.add(asset)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="asset_id already exists") from exc
    db.refresh(asset)
    return asset_to_schema(asset)


@app.get("/api/super-grok/animation-prompts", response_model=list[SuperGrokPromptRead])
def list_super_grok_prompts(
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[SuperGrokPromptPackage]:
    query = select(SuperGrokPromptPackage).order_by(SuperGrokPromptPackage.created_at.desc()).limit(limit)
    if status:
        query = query.where(SuperGrokPromptPackage.status == status)
    return list(db.scalars(query))


@app.post("/api/super-grok/animation-prompts", response_model=SuperGrokPromptRead, status_code=201)
def create_super_grok_prompt(payload: SuperGrokPromptCreate, db: Session = Depends(get_db)) -> SuperGrokPromptPackage:
    if not payload.reference_image_path and not payload.asset_id:
        raise HTTPException(422, detail="reference_image_path or asset_id is required")

    asset = None
    reference_value = payload.reference_image_path
    if payload.asset_id:
        asset = db.scalar(select(Asset).where(Asset.asset_id == payload.asset_id))
        if not asset:
            raise HTTPException(404, detail=f"Asset not found: {payload.asset_id}")
        reference_value = reference_value or asset.file_path

    assert reference_value is not None
    reference_path = resolve_workspace_path(reference_value)
    if reference_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not reference_path.is_file():
        raise HTTPException(422, detail="Reference image must be an existing PNG/JPG/WebP file in the workspace")

    relative_reference = reference_path.relative_to(settings.resolved_workspace_root).as_posix()
    prompt, negative_prompt, package_payload = build_super_grok_prompt(payload, relative_reference)
    package_id = str(uuid4())
    output_dir = settings.resolved_workspace_root / "07_cinematics" / "work" / "super_grok_requests"
    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / f"{package_id}.json"
    markdown_path = output_dir / f"{package_id}.md"
    relative_package_path = package_path.relative_to(settings.resolved_workspace_root).as_posix()
    package_payload.update(
        {
            "id": package_id,
            "package_path": relative_package_path,
            "markdown_path": markdown_path.relative_to(settings.resolved_workspace_root).as_posix(),
            "source_asset_file_path": asset.file_path if asset else None,
        }
    )
    package_path.write_text(json.dumps(package_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        "\n".join(
            [
                f"# {payload.title}",
                "",
                "## SuperGrok prompt",
                prompt,
                "",
                "## Negative prompt",
                negative_prompt,
                "",
                f"Reference image: {relative_reference}",
            ]
        ),
        encoding="utf-8",
    )

    package = SuperGrokPromptPackage(
        id=package_id,
        source_task_id=payload.source_task_id,
        asset_id=payload.asset_id,
        title=payload.title,
        request_type=payload.request_type,
        status="READY",
        reference_image_path=relative_reference,
        prompt=prompt,
        negative_prompt=negative_prompt,
        package_path=relative_package_path,
        package_payload=package_payload,
        created_by=payload.created_by,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


@app.get("/api/approvals", response_model=list[ApprovalRead])
def list_approvals(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Approval]:
    query = select(Approval).order_by(Approval.created_at.desc()).limit(limit)
    if status:
        query = query.where(Approval.status == status)
    return list(db.scalars(query))


@app.post("/api/approvals", response_model=ApprovalRead, status_code=201)
def create_approval(payload: ApprovalCreate, db: Session = Depends(get_db)) -> Approval:
    task = db.get(Task, payload.task_id)
    if not task:
        raise HTTPException(404, detail="Task not found")
    assets = []
    for asset_id in dict.fromkeys(payload.asset_ids):
        asset = db.scalar(select(Asset).where(Asset.asset_id == asset_id))
        if not asset:
            raise HTTPException(404, detail=f"Asset not found: {asset_id}")
        assets.append(asset)
    approval = Approval(**payload.model_dump(exclude={"asset_ids"}))
    task.status = "WAITING_USER_APPROVAL"
    db.add(approval)
    db.flush()
    for asset in assets:
        db.add(ApprovalAsset(approval_id=approval.id, asset_id=asset.asset_id))
    db.commit()
    db.refresh(approval)
    return approval


@app.post("/api/approvals/{approval_id}/decision", response_model=ApprovalRead)
def decide_approval(approval_id: str, payload: ApprovalDecision, db: Session = Depends(get_db)) -> Approval:
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(404, detail="Approval not found")
    if approval.status != "PENDING":
        raise HTTPException(409, detail="Approval was already decided")
    approval.status = payload.decision
    approval.decision_note = payload.decision_note
    approval.decided_by = payload.decided_by
    approval.decided_at = datetime.now(timezone.utc)
    approval.task.status = "APPROVED" if payload.decision == "APPROVED" else "REVISION_REQUIRED"
    if payload.decision == "APPROVED":
        try:
            promote_approved_assets(db, approval, settings.resolved_workspace_root)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        queue_game_dispatch(
            db,
            approval.task,
            approval,
            load_agents(),
            settings.resolved_workspace_root,
        )
    elif payload.decision == "REVISION_REQUIRED":
        for link in approval.linked_assets:
            link.asset.status = "REVISION_REQUIRED"
    db.commit()
    db.refresh(approval)
    return approval


@app.get("/api/dispatches", response_model=list[DispatchRead])
def list_dispatches(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Dispatch]:
    query = select(Dispatch).order_by(Dispatch.created_at.desc()).limit(limit)
    if status:
        query = query.where(Dispatch.status == status)
    return list(db.scalars(query))


@app.post("/api/dispatches/{dispatch_id}/claim", response_model=DispatchRead)
def claim_dispatch(dispatch_id: str, db: Session = Depends(get_db)) -> Dispatch:
    dispatch = db.get(Dispatch, dispatch_id)
    if not dispatch:
        raise HTTPException(404, detail="Dispatch not found")
    if dispatch.status != "PENDING":
        raise HTTPException(409, detail=f"Dispatch is already {dispatch.status}")
    dispatch.status = "CLAIMED"
    dispatch.attempts += 1
    dispatch.claimed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dispatch)
    return dispatch


@app.patch("/api/dispatches/{dispatch_id}", response_model=DispatchRead)
def finish_dispatch(
    dispatch_id: str,
    payload: DispatchStatusUpdate,
    db: Session = Depends(get_db),
) -> Dispatch:
    dispatch = db.get(Dispatch, dispatch_id)
    if not dispatch:
        raise HTTPException(404, detail="Dispatch not found")
    if dispatch.status != "CLAIMED":
        raise HTTPException(409, detail="Dispatch must be claimed first")
    dispatch.status = payload.status
    dispatch.last_error = payload.last_error
    if payload.status == "SENT":
        dispatch.sent_at = datetime.now(timezone.utc)
        if dispatch.target_task_id:
            target_task = db.get(Task, dispatch.target_task_id)
            if target_task:
                output_payload = target_task.output_payload or {}
                if output_payload.get("paused_by_pm"):
                    target_task.status = "PAUSED"
                else:
                    target_task.status = "RUNNING"
    db.commit()
    db.refresh(dispatch)
    return dispatch


@app.post("/api/pipeline/roles/{role}/pause")
def pause_pipeline_role(role: str, reason: str = "manual_pm_pause", db: Session = Depends(get_db)) -> dict:
    try:
        find_worker(load_agents(), role)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    tasks = list(db.scalars(select(Task).where(Task.assignee_role == role, Task.status.in_(["READY", "RUNNING"]))))
    for task in tasks:
        task.status = "PAUSED"
        task.output_payload = {
            **(task.output_payload or {}),
            "paused_by_pm": True,
            "pause_reason": reason,
            "paused_at": datetime.now(timezone.utc).isoformat(),
        }
    db.commit()
    return {"role": role, "paused_tasks": len(tasks), "reason": reason}


@app.post("/api/pipeline/roles/{role}/resume")
def resume_pipeline_role(role: str, db: Session = Depends(get_db)) -> dict:
    try:
        find_worker(load_agents(), role)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    tasks = list(db.scalars(select(Task).where(Task.assignee_role == role, Task.status == "PAUSED")))
    for task in tasks:
        output_payload = {**(task.output_payload or {})}
        output_payload["paused_by_pm"] = False
        output_payload["resumed_at"] = datetime.now(timezone.utc).isoformat()
        task.output_payload = output_payload
        task.status = "READY"
    db.commit()
    return {"role": role, "resumed_tasks": len(tasks)}


@app.get("/api/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)) -> dict:
    return {
        "stages": pipeline_stage_status(db),
        "pending_dispatches": db.scalar(select(func.count()).select_from(Dispatch).where(Dispatch.status == "PENDING")),
        "running_tasks": db.scalar(select(func.count()).select_from(Task).where(Task.status == "RUNNING")),
        "paused_tasks": db.scalar(select(func.count()).select_from(Task).where(Task.status == "PAUSED")),
        "mcp": {
            "server_name": "game_production_pm",
            "registered_in_codex_config": True,
            "hub_url": "http://127.0.0.1:8000",
        },
        "architecture": pipeline_architecture_status(db),
    }


@app.get("/api/pipeline/architecture")
def pipeline_architecture(db: Session = Depends(get_db)) -> dict:
    return pipeline_architecture_status(db)


@app.post("/api/dispatches/{dispatch_id}/retry", response_model=DispatchRead)
def retry_dispatch(dispatch_id: str, db: Session = Depends(get_db)) -> Dispatch:
    dispatch = db.get(Dispatch, dispatch_id)
    if not dispatch:
        raise HTTPException(404, detail="Dispatch not found")
    if dispatch.status != "FAILED":
        raise HTTPException(409, detail=f"Only FAILED dispatches can be retried; current status is {dispatch.status}")
    dispatch.status = "PENDING"
    dispatch.last_error = None
    dispatch.claimed_at = None
    dispatch.sent_at = None
    db.commit()
    db.refresh(dispatch)
    return dispatch


@app.get("/api/runtime-reports", response_model=list[RuntimeReportRead])
def list_runtime_reports(
    task_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[RuntimeReport]:
    query = select(RuntimeReport).order_by(RuntimeReport.created_at.desc()).limit(limit)
    if task_id:
        query = query.where(RuntimeReport.task_id == task_id)
    return list(db.scalars(query))


@app.post("/api/runtime-reports", response_model=RuntimeReportRead, status_code=201)
def create_runtime_report(payload: RuntimeReportCreate, db: Session = Depends(get_db)) -> RuntimeReport:
    task = db.get(Task, payload.task_id)
    if not task:
        raise HTTPException(404, detail="Task not found")
    report_path = resolve_workspace_path(payload.report_path)
    if report_path.suffix.lower() != ".json" or not report_path.is_file():
        raise HTTPException(422, detail="Runtime report must be an existing JSON file")
    try:
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(422, detail="Runtime report JSON is invalid") from exc
    if not isinstance(report_payload, dict):
        raise HTTPException(422, detail="Runtime report root must be an object")
    normalized_captures = []
    for capture_value in payload.capture_paths:
        capture = resolve_workspace_path(capture_value)
        if capture.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"} or not capture.is_file():
            raise HTTPException(422, detail=f"Runtime capture is invalid: {capture_value}")
        normalized_captures.append(capture.relative_to(settings.resolved_workspace_root).as_posix())
    success = str(report_payload.get("status", "")).upper() == "SUCCESS"
    report = RuntimeReport(
        task_id=task.id,
        asset_id=payload.asset_id or report_payload.get("asset_id"),
        status="PASS" if success else "FAIL",
        report_path=report_path.relative_to(settings.resolved_workspace_root).as_posix(),
        capture_paths=normalized_captures,
        report_payload=report_payload,
    )
    task.status = "RUNTIME_QA" if success else "REVISION_REQUIRED"
    task.output_payload = {**(task.output_payload or {}), "runtime_report": report_payload, "captures": normalized_captures}
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@app.post("/api/usage", response_model=ApiUsageRead, status_code=201)
def record_usage(payload: ApiUsageCreate, db: Session = Depends(get_db)) -> ApiUsage:
    usage = ApiUsage(**payload.model_dump())
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def monthly_provider_costs(db: Session) -> dict:
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return dict(
        db.execute(
            select(
                ApiUsage.provider,
                func.coalesce(func.sum(func.coalesce(ApiUsage.actual_cost_usd, ApiUsage.estimated_cost_usd)), 0),
            )
            .where(ApiUsage.created_at >= month_start)
            .group_by(ApiUsage.provider)
        ).all()
    )


@app.get("/api/gateway/policy")
def gateway_policy(db: Session = Depends(get_db)) -> dict:
    costs = monthly_provider_costs(db)
    return {
        "external_calls_enabled": settings.external_ai_calls_enabled,
        "default_policy": settings.gateway_default_policy,
        "monthly_cost_usd": costs,
        "budgets": {
            "claude": {
                "hard": settings.claude_monthly_budget_usd,
                "soft": settings.claude_soft_limit_usd,
                "stop": settings.claude_stop_limit_usd,
            },
            "openai": {"hard": settings.openai_monthly_budget_usd},
        },
        "rules": [
            "허브가 승인한 큐 항목만 처리한다.",
            "기본 설정에서는 외부 AI API를 호출하지 않고 사용량/비용/실패만 기록한다.",
            "provider별 hard/stop 한도 초과 시 WAITING_BUDGET_RESET로 넘긴다.",
        ],
    }


@app.post("/api/gateway/check")
def gateway_check(payload: ApiUsageCreate, db: Session = Depends(get_db)) -> dict:
    costs = monthly_provider_costs(db)
    provider = payload.provider.lower()
    projected_cost = float(costs.get(provider, 0)) + float(payload.actual_cost_usd or payload.estimated_cost_usd or 0)
    hard_limit = {
        "claude": settings.claude_stop_limit_usd,
        "openai": settings.openai_monthly_budget_usd,
    }.get(provider, 0)
    budget_allows = hard_limit <= 0 or projected_cost <= hard_limit
    allowed = bool(settings.external_ai_calls_enabled and budget_allows)
    reason = "allowed"
    if not settings.external_ai_calls_enabled:
        reason = "external_ai_calls_disabled"
    elif not budget_allows:
        reason = "budget_limit_exceeded"
    return {
        "allowed": allowed,
        "reason": reason,
        "provider": provider,
        "projected_monthly_cost_usd": projected_cost,
        "limit_usd": hard_limit,
        "policy": settings.gateway_default_policy,
    }


@app.get("/api/dashboard")
def dashboard_data(db: Session = Depends(get_db)) -> dict:
    tasks = list(db.scalars(select(Task).order_by(Task.updated_at.desc()).limit(12)))
    pending = list(
        db.scalars(
            select(Approval)
            .where(Approval.status == "PENDING")
            .order_by(Approval.created_at.desc())
            .limit(12)
        )
    )
    recent_dispatches = list(db.scalars(select(Dispatch).order_by(Dispatch.created_at.desc()).limit(12)))
    recent_runtime_reports = list(
        db.scalars(select(RuntimeReport).order_by(RuntimeReport.created_at.desc()).limit(12))
    )
    recent_super_grok_prompts = list(
        db.scalars(select(SuperGrokPromptPackage).order_by(SuperGrokPromptPackage.created_at.desc()).limit(6))
    )
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    costs = monthly_provider_costs(db)
    asset_counts = Counter(asset.status for asset in db.scalars(select(Asset)))
    dispatch_counts = Counter(item.status for item in db.scalars(select(Dispatch)))
    runtime_counts = Counter(item.status for item in db.scalars(select(RuntimeReport)))
    return {
        "counts": Counter(task.status for task in db.scalars(select(Task))),
        "asset_counts": asset_counts,
        "dispatch_counts": dispatch_counts,
        "runtime_counts": runtime_counts,
        "pipeline_stages": pipeline_stage_status(db),
        "pm_routing": pipeline_architecture_status(db),
        "recent_tasks": [TaskRead.model_validate(task) for task in tasks],
        "pending_approvals": [ApprovalRead.model_validate(item) for item in pending],
        "recent_dispatches": [DispatchRead.model_validate(item) for item in recent_dispatches],
        "recent_runtime_reports": [RuntimeReportRead.model_validate(item) for item in recent_runtime_reports],
        "recent_super_grok_prompts": [SuperGrokPromptRead.model_validate(item) for item in recent_super_grok_prompts],
        "monthly_cost_usd": costs,
        "budgets": {
            "claude": {
                "hard": settings.claude_monthly_budget_usd,
                "soft": settings.claude_soft_limit_usd,
                "stop": settings.claude_stop_limit_usd,
            },
            "openai": {"hard": settings.openai_monthly_budget_usd},
        },
        "agents": load_agents(),
    }
