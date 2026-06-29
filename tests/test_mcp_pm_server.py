import json

from mcp_server.pm_server import HubResponse, call_tool, handle_request, tool_schema


def fake_hub(method, path, payload=None):
    return HubResponse(200, {"method": method, "path": path, "payload": payload})


def test_mcp_lists_pm_tools():
    names = {item["name"] for item in tool_schema()}
    assert "create_pipeline_task" in names
    assert "get_pipeline_status" in names
    assert "get_pipeline_controls" in names
    assert "pause_pipeline_role" in names
    assert "resume_pipeline_role" in names
    assert "register_runtime_report" in names


def test_mcp_create_pipeline_task_calls_hub():
    result = call_tool(
        "create_pipeline_task",
        {
            "title": "시장 조사",
            "task_type": "market_research",
            "assignee_role": "planning_research",
            "input_payload": {"topic": "idle RPG"},
        },
        hub_request=fake_hub,
    )
    assert result["method"] == "POST"
    assert result["path"] == "/api/tasks"
    assert result["payload"]["assignee_role"] == "planning_research"


def test_mcp_jsonrpc_tools_call_result():
    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response["id"] == 1
    assert any(tool["name"] == "queue_dispatch" for tool in response["result"]["tools"])


def test_mcp_result_is_text_json():
    value = call_tool("list_pending_dispatches", {}, hub_request=fake_hub)
    assert value["path"] == "/api/dispatches?status=PENDING"
    response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "initialize"})
    assert json.loads(json.dumps(response))["result"]["serverInfo"]["name"] == "game-production-pm"


def test_mcp_pause_role_calls_hub():
    result = call_tool(
        "pause_pipeline_role",
        {"role": "game_development", "reason": "manual stop"},
        hub_request=fake_hub,
    )
    assert result["method"] == "POST"
    assert result["path"] == "/api/pipeline/roles/game_development/pause?reason=manual%20stop"
