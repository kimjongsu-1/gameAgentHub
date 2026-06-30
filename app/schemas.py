from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TASK_STATUSES = (
    "PLANNED",
    "READY",
    "RUNNING",
    "PAUSED",
    "DESIGNING",
    "SPRITE_GENERATING",
    "QA_RUNNING",
    "REVISION_REQUIRED",
    "WAITING_API_RESET",
    "WAITING_BUDGET_RESET",
    "WAITING_USER_APPROVAL",
    "APPROVED",
    "INTEGRATING",
    "RUNTIME_QA",
    "CINEMATIC_RENDERING",
    "COMPLETED",
    "FAILED",
)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    task_type: str = Field(min_length=1, max_length=80)
    assignee_role: str = Field(min_length=1, max_length=80)
    assignee_thread_id: str | None = None
    priority: int = Field(default=100, ge=0, le=1000)
    input_payload: dict[str, Any] = Field(default_factory=dict)


class TaskStatusUpdate(BaseModel):
    status: str
    output_payload: dict[str, Any] | None = None
    resume_at: datetime | None = None


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    output_payload: dict[str, Any] | None
    resume_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssetCreate(BaseModel):
    asset_id: str
    asset_type: str
    character_version: str
    style_version: str
    source_asset: str
    file_path: str
    frame_count: int | None = Field(default=None, ge=1)
    fps: float | None = Field(default=None, gt=0)
    loop: bool | None = None
    pivot: dict[str, float] | None = None
    status: str = "WORKING"
    checksum: str
    created_by: str
    approved_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetRead(AssetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class ApprovalCreate(BaseModel):
    task_id: str
    approval_type: str
    summary: str
    preview_paths: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    asset_ids: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "REVISION_REQUIRED"]
    decision_note: str | None = None
    decided_by: str = "user"


class ApprovalRead(ApprovalCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    decision_note: str | None
    decided_by: str | None
    created_at: datetime
    decided_at: datetime | None


class ApiUsageCreate(BaseModel):
    provider: str
    model: str
    task_id: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0)
    actual_cost_usd: float | None = Field(default=None, ge=0)
    http_status: int | None = None
    request_id: str | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0)
    resume_at: datetime | None = None


class ApiUsageRead(ApiUsageCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class SpriteQARunRequest(BaseModel):
    source_path: str
    output_dir: str | None = None
    task_id: str | None = None
    asset_id: str | None = None
    columns: int = Field(default=4, ge=1, le=32)
    rows: int = Field(default=4, ge=1, le=32)
    expected_frames: int = Field(default=16, ge=1, le=256)
    fps: float = Field(default=12, gt=0, le=120)
    loop: bool = True
    chroma_key: str | None = None
    chroma_tolerance: int = Field(default=45, ge=0, le=255)


class HandoffPackageRead(BaseModel):
    task_id: str
    target_role: str
    target_thread_id: str
    target_thread_title: str
    design_profile_id: str | None = None
    design_profile_name: str | None = None
    prompt_profile: str | None = None
    markdown_path: str
    json_path: str
    prompt: str


class DispatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_task_id: str
    target_task_id: str | None
    approval_id: str | None
    target_role: str
    target_thread_id: str
    target_thread_title: str
    status: str
    prompt: str
    dispatch_payload: dict[str, Any]
    attempts: int
    last_error: str | None
    created_at: datetime
    claimed_at: datetime | None
    sent_at: datetime | None


class DispatchStatusUpdate(BaseModel):
    status: Literal["SENT", "FAILED"]
    last_error: str | None = None


class RuntimeReportCreate(BaseModel):
    task_id: str
    asset_id: str | None = None
    report_path: str
    capture_paths: list[str] = Field(default_factory=list)


class RuntimeReportRead(RuntimeReportCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    report_payload: dict[str, Any]
    created_at: datetime


class SuperGrokPromptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    request_type: Literal["skill_animation", "cutscene"] = "skill_animation"
    reference_image_path: str | None = None
    asset_id: str | None = None
    source_task_id: str | None = None
    character_name: str | None = None
    animation_goal: str = Field(min_length=1, max_length=500)
    style_notes: str | None = None
    duration_seconds: float = Field(default=3.0, gt=0, le=30)
    aspect_ratio: str = "1:1"
    created_by: str = "pm"


class SuperGrokPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_task_id: str | None
    asset_id: str | None
    title: str
    request_type: str
    status: str
    reference_image_path: str
    prompt: str
    negative_prompt: str | None
    package_path: str
    package_payload: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime


class GameBibleUpdate(BaseModel):
    content: str
    notes: str | None = None
