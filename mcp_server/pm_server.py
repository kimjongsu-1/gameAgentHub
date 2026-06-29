"""Minimal MCP stdio server for the game production PM.

The MCP server is the "총괄 PM" surface. It does not own a second database.
Instead, it exposes safe tools that call the local FastAPI control hub.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


HUB_URL = os.environ.get("GAME_HUB_URL", "http://127.0.0.1:8000").rstrip("/")


@dataclass(frozen=True)
class HubResponse:
    status: int
    body: Any


class MCPToolError(ValueError):
    pass


def http_json(method: str, path: str, payload: dict[str, Any] | None = None) -> HubResponse:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{HUB_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return HubResponse(response.status, json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw}
        raise MCPToolError(f"Hub API {method} {path} failed: {exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise MCPToolError(f"Hub API is unavailable at {HUB_URL}: {exc.reason}") from exc


def tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_pipeline_status",
            "description": "Return dashboard counts, recent tasks, approvals, dispatches, runtime reports, and budgets.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_pipeline_controls",
            "description": "Return operational pipeline stage, MCP, paused, running, and pending dispatch status.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_workers",
            "description": "Return configured PM workers, including planning, design, and game development roles.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "create_pipeline_task",
            "description": "Create a PM-managed task for planning, design, or game development.",
            "inputSchema": {
                "type": "object",
                "required": ["title", "task_type", "assignee_role"],
                "properties": {
                    "title": {"type": "string"},
                    "task_type": {"type": "string"},
                    "assignee_role": {"type": "string"},
                    "priority": {"type": "integer", "default": 100},
                    "input_payload": {"type": "object", "default": {}},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_handoff_package",
            "description": "Create a markdown/json handoff package for an existing task.",
            "inputSchema": {
                "type": "object",
                "required": ["task_id"],
                "properties": {"task_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "queue_dispatch",
            "description": "Queue a task dispatch to its configured Codex worker thread.",
            "inputSchema": {
                "type": "object",
                "required": ["task_id"],
                "properties": {"task_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "list_pending_dispatches",
            "description": "List dispatches waiting to be sent to worker threads.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "claim_dispatch",
            "description": "Claim a pending dispatch before sending it.",
            "inputSchema": {
                "type": "object",
                "required": ["dispatch_id"],
                "properties": {"dispatch_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "mark_dispatch_sent",
            "description": "Mark a claimed dispatch as sent.",
            "inputSchema": {
                "type": "object",
                "required": ["dispatch_id"],
                "properties": {"dispatch_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "mark_dispatch_failed",
            "description": "Mark a claimed dispatch as failed with an error summary.",
            "inputSchema": {
                "type": "object",
                "required": ["dispatch_id", "last_error"],
                "properties": {
                    "dispatch_id": {"type": "string"},
                    "last_error": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "pause_pipeline_role",
            "description": "Pause READY/RUNNING tasks for a worker role without deleting work.",
            "inputSchema": {
                "type": "object",
                "required": ["role"],
                "properties": {
                    "role": {"type": "string"},
                    "reason": {"type": "string", "default": "manual_pm_pause"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "resume_pipeline_role",
            "description": "Resume PAUSED tasks for a worker role back to READY.",
            "inputSchema": {
                "type": "object",
                "required": ["role"],
                "properties": {"role": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "register_runtime_report",
            "description": "Register a Unity/runtime report and optional capture paths back into the PM hub.",
            "inputSchema": {
                "type": "object",
                "required": ["task_id", "report_path"],
                "properties": {
                    "task_id": {"type": "string"},
                    "asset_id": {"type": "string"},
                    "report_path": {"type": "string"},
                    "capture_paths": {"type": "array", "items": {"type": "string"}, "default": []},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_gateway_policy",
            "description": "Return external AI call policy, provider budgets, and current monthly usage.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def call_tool(
    name: str,
    arguments: dict[str, Any],
    hub_request: Callable[[str, str, dict[str, Any] | None], HubResponse] = http_json,
) -> Any:
    if name == "get_pipeline_status":
        return hub_request("GET", "/api/dashboard", None).body
    if name == "get_pipeline_controls":
        return hub_request("GET", "/api/pipeline/status", None).body
    if name == "list_workers":
        return hub_request("GET", "/api/agents", None).body
    if name == "create_pipeline_task":
        payload = {
            "title": arguments["title"],
            "task_type": arguments["task_type"],
            "assignee_role": arguments["assignee_role"],
            "priority": arguments.get("priority", 100),
            "input_payload": arguments.get("input_payload", {}),
        }
        return hub_request("POST", "/api/tasks", payload).body
    if name == "create_handoff_package":
        return hub_request("POST", f"/api/tasks/{arguments['task_id']}/handoff-package", {}).body
    if name == "queue_dispatch":
        return hub_request("POST", f"/api/tasks/{arguments['task_id']}/queue-dispatch", {}).body
    if name == "list_pending_dispatches":
        return hub_request("GET", "/api/dispatches?status=PENDING", None).body
    if name == "claim_dispatch":
        return hub_request("POST", f"/api/dispatches/{arguments['dispatch_id']}/claim", {}).body
    if name == "mark_dispatch_sent":
        return hub_request("PATCH", f"/api/dispatches/{arguments['dispatch_id']}", {"status": "SENT"}).body
    if name == "mark_dispatch_failed":
        return hub_request(
            "PATCH",
            f"/api/dispatches/{arguments['dispatch_id']}",
            {"status": "FAILED", "last_error": arguments["last_error"]},
        ).body
    if name == "pause_pipeline_role":
        reason = urllib.parse.quote(arguments.get("reason", "manual_pm_pause"))
        return hub_request("POST", f"/api/pipeline/roles/{arguments['role']}/pause?reason={reason}", {}).body
    if name == "resume_pipeline_role":
        return hub_request("POST", f"/api/pipeline/roles/{arguments['role']}/resume", {}).body
    if name == "register_runtime_report":
        return hub_request(
            "POST",
            "/api/runtime-reports",
            {
                "task_id": arguments["task_id"],
                "asset_id": arguments.get("asset_id"),
                "report_path": arguments["report_path"],
                "capture_paths": arguments.get("capture_paths", []),
            },
        ).body
    if name == "get_gateway_policy":
        return hub_request("GET", "/api/gateway/policy", None).body
    raise MCPToolError(f"Unknown MCP tool: {name}")


def mcp_result(value: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, indent=2),
            }
        ]
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "game-production-pm", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": tool_schema()}
        elif method == "tools/call":
            params = message.get("params", {})
            result = mcp_result(call_tool(params["name"], params.get("arguments", {})))
        else:
            raise MCPToolError(f"Unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
