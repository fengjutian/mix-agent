"""管理后台 API — 成本看板、模型配置、API Key 管理。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mix_agent.api.deps import require_admin
from mix_agent.services.cost_manager import cost_manager
from mix_agent.services.node_config import list_nodes, list_models, set_node_provider
from mix_agent.services.llm import MODEL_REGISTRY
from mix_agent.services import key_store

from mix_agent.services.prompt_store import prompt_store
from mix_agent.services.mcp_store import mcp_store, MCPServerConfig
from mix_agent.services.mcp_client import MCPClient, MCPTestResult

router = APIRouter()


# ── Cost ──

@router.get("/cost/overview")
def cost_overview(user: dict = Depends(require_admin)):
    """成本概览：总成本、总调用次数、活跃任务数。"""
    return cost_manager.overview()


@router.get("/cost/breakdown")
def cost_breakdown(user: dict = Depends(require_admin)):
    """按任务拆解成本：每任务的 cost/calls/budget/usage%。"""
    return {
        "tasks": cost_manager.breakdown_by_task(),
    }


# ── Models ──

@router.get("/models")
def get_models(user: dict = Depends(require_admin)):
    """返回已注册模型列表 + 各 agent 节点的当前 provider 分配。"""
    return {
        "models": list_models(),
        "nodes": list_nodes(),
    }


class AssignModelBody(BaseModel):
    node: str
    provider: str


@router.put("/models/assign")
def assign_model(body: AssignModelBody, user: dict = Depends(require_admin)):
    """将指定 agent 节点切换到另一个 provider。

    Example: {"node": "code_review", "provider": "minimax"}
    """
    node = body.node.strip()
    provider = body.provider.strip()

    # 校验 provider 是否存在
    if provider not in MODEL_REGISTRY:
        known = list(MODEL_REGISTRY.keys())
        return {"ok": False, "error": f"Unknown provider '{provider}'. Available: {known}"}

    ok = set_node_provider(node, provider)
    if not ok:
        return {
            "ok": False,
            "error": f"Unknown node '{node}'. Available: {list(list_nodes())}",
        }

    return {"ok": True, "node": node, "provider": provider}


# ── API Keys ──

@router.get("/keys")
def get_keys(user: dict = Depends(require_admin)):
    """返回所有已配置的 API key（加密遮盖）。"""
    return {"keys": key_store.list_keys()}


class SetKeyBody(BaseModel):
    provider: str
    api_key: str
    base_url: str = ""
    model: str = ""


@router.put("/keys")
def set_key(body: SetKeyBody, user: dict = Depends(require_admin)):
    """设置/更新某个 provider 的 API key。

    Example: {"provider": "openai", "api_key": "sk-xxx", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"}
    """
    provider = body.provider.strip().lower()
    if not provider:
        return {"ok": False, "error": "Provider name is required."}

    ok = key_store.set_key(provider, body.api_key.strip(), body.base_url.strip(), body.model.strip())
    return {"ok": ok, "provider": provider}


class DeleteKeyBody(BaseModel):
    provider: str


@router.delete("/keys")
def delete_key(body: DeleteKeyBody, user: dict = Depends(require_admin)):
    """删除某个 provider 的 API key 配置。"""
    provider = body.provider.strip().lower()
    ok = key_store.delete_key(provider)
    if not ok:
        return {"ok": False, "error": f"Provider '{provider}' not found."}
    return {"ok": True, "provider": provider}


# ── Prompts ──

@router.get("/prompts")
def get_prompts(user: dict = Depends(require_admin)):
    """返回所有 agent 的当前 prompt 模板。"""
    return {"prompts": prompt_store.list_all()}


class UpdatePromptBody(BaseModel):
    system: str | None = None
    user_template: str | None = None


@router.put("/prompts/{agent}")
def update_prompt(agent: str, body: UpdatePromptBody, user: dict = Depends(require_admin)):
    """更新指定 agent 的 prompt 模板。

    Example: PUT /admin/prompts/code_review
    {"system": "你是一名代码审查专家...", "user_template": "{input}"}
    """
    ok = prompt_store.update(
        agent,
        system=body.system,
        user_template=body.user_template,
    )
    if not ok:
        known = [p["agent"] for p in prompt_store.list_all()]
        return {"ok": False, "error": f"Unknown agent '{agent}'. Available: {known}"}
    return {"ok": True, "agent": agent}


@router.delete("/prompts/{agent}")
def reset_prompt(agent: str, user: dict = Depends(require_admin)):
    """重置指定 agent 的 prompt 为内置默认值。"""
    ok = prompt_store.reset(agent)
    if not ok:
        known = [p["agent"] for p in prompt_store.list_all()]
        return {"ok": False, "error": f"Unknown agent '{agent}'. Available: {known}"}
    return {"ok": True, "agent": agent, "message": "Reset to default"}


# ── MCP Servers ──

@router.get("/mcp/servers")
def list_mcp_servers(user: dict = Depends(require_admin)):
    """返回所有已配置的 MCP 服务器列表。"""
    servers = mcp_store.list_all()
    return {"servers": [s.to_dict() for s in servers]}


class AddMCPServerBody(BaseModel):
    name: str
    transport: str = "stdio"
    enabled: bool = True
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    url: str = ""
    headers: dict[str, str] = {}


@router.post("/mcp/servers")
def add_mcp_server(body: AddMCPServerBody, user: dict = Depends(require_admin)):
    """添加新的 MCP 服务器配置。"""
    if body.transport not in ("stdio", "http", "sse"):
        return {"ok": False, "error": f"Invalid transport '{body.transport}'. Use stdio/http/sse."}

    cfg = MCPServerConfig(
        name=body.name.strip(),
        transport=body.transport,  # type: ignore
        enabled=body.enabled,
        command=body.command.strip(),
        args=body.args,
        env=body.env,
        url=body.url.strip(),
        headers=body.headers,
    )

    ok = mcp_store.add(cfg)
    if not ok:
        return {"ok": False, "error": f"Server '{body.name}' already exists or name is empty."}
    return {"ok": True, "server": cfg.to_dict()}


class UpdateMCPServerBody(BaseModel):
    transport: str | None = None
    enabled: bool | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


@router.put("/mcp/servers/{name}")
def update_mcp_server(name: str, body: UpdateMCPServerBody, user: dict = Depends(require_admin)):
    """更新 MCP 服务器配置（部分更新）。"""
    updates = {}
    if body.transport is not None:
        if body.transport not in ("stdio", "http", "sse"):
            return {"ok": False, "error": f"Invalid transport '{body.transport}'."}
        updates["transport"] = body.transport
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.command is not None:
        updates["command"] = body.command
    if body.args is not None:
        updates["args"] = body.args
    if body.env is not None:
        updates["env"] = body.env
    if body.url is not None:
        updates["url"] = body.url
    if body.headers is not None:
        updates["headers"] = body.headers

    ok = mcp_store.update(name, updates)
    if not ok:
        return {"ok": False, "error": f"Server '{name}' not found."}

    updated = mcp_store.get(name)
    return {"ok": True, "server": updated.to_dict() if updated else None}


@router.delete("/mcp/servers/{name}")
def delete_mcp_server(name: str, user: dict = Depends(require_admin)):
    """删除 MCP 服务器配置。"""
    ok = mcp_store.delete(name)
    if not ok:
        return {"ok": False, "error": f"Server '{name}' not found."}
    return {"ok": True, "name": name}


@router.post("/mcp/servers/{name}/test")
async def test_mcp_server(name: str, user: dict = Depends(require_admin)):
    """测试 MCP 服务器连接。"""
    cfg = mcp_store.get(name)
    if not cfg:
        return {"ok": False, "error": f"Server '{name}' not found."}

    client = MCPClient(cfg)
    result = await client.test_connection()

    return {
        "ok": result.ok,
        "server_name": result.server_name,
        "server_version": result.server_version,
        "tools": [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in result.tools
        ],
        "error": result.error,
    }
