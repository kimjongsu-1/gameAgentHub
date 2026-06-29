import json
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.handoff import build_handoff_package, find_worker
from app.models import ApiUsage, Approval, ApprovalAsset, Asset, Dispatch, RuntimeReport, Task
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


def pipeline_stage_status(db: Session) -> list[dict]:
    agents = load_agents()
    role_names = ["planning_research", "design_orchestra", "game_development"]
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
    }


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
        "recent_tasks": [TaskRead.model_validate(task) for task in tasks],
        "pending_approvals": [ApprovalRead.model_validate(item) for item in pending],
        "recent_dispatches": [DispatchRead.model_validate(item) for item in recent_dispatches],
        "recent_runtime_reports": [RuntimeReportRead.model_validate(item) for item in recent_runtime_reports],
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
