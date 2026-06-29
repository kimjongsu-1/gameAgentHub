import json

from mcp_server.pm_server import HubResponse, call_tool, handle_request, tool_schema


def fake_hub(method, path, payload=None):
    return HubResponse(200, {"method": method, "path": path, "payload": payload})


def test_mcp_lists_pm_tools():
    names = {item["name"] for item in tool_schema()}
    assert "create_pipeline_task" in names
    assert "get_pipeline_status" in names
    assert "get_pipeline_controls" in names
    assert "get_pm_routing_architecture" in names
    assert "pause_pipeline_role" in names
    assert "resume_pipeline_role" in names
    assert "register_runtime_report" in names
    assert "create_super_grok_animation_prompt" in names


def test_mcp_create_pipeline_task_calls_hub():
    result = call_tool(
        "create_pipeline_task",
        {
            "title": "주인공 16프레임 제작",
            "task_type": "sprite_16_frame",
            "assignee_role": "design_orchestra",
            "input_payload": {"user_planning": "idle RPG hero"},
        },
        hub_request=fake_hub,
    )
    assert result["method"] == "POST"
    assert result["path"] == "/api/tasks"
    assert result["payload"]["assignee_role"] == "design_orchestra"


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


def test_mcp_pm_routing_architecture_calls_hub():
    result = call_tool("get_pm_routing_architecture", {}, hub_request=fake_hub)
    assert result["method"] == "GET"
    assert result["path"] == "/api/pipeline/architecture"


def test_mcp_create_super_grok_animation_prompt_calls_hub():
    result = call_tool(
        "create_super_grok_animation_prompt",
        {
            "title": "Hero skill animation",
            "reference_image_path": "03_character_masters/hero.png",
            "character_name": "Hero",
            "animation_goal": "A short sword slash skill animation.",
        },
        hub_request=fake_hub,
    )
    assert result["method"] == "POST"
    assert result["path"] == "/api/super-grok/animation-prompts"
    assert result["payload"]["created_by"] == "mcp_pm"
    assert result["payload"]["animation_goal"] == "A short sword slash skill animation."
