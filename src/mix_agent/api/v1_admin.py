"""管理后台 API — 成本看板、模型配置、API Key 管理。"""

import json

from fastapi import APIRouter
from pydantic import BaseModel

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
def cost_overview():
    """成本概览：总成本、总调用次数、活跃任务数。"""
    return cost_manager.overview()


@router.get("/cost/breakdown")
def cost_breakdown():
    """按任务拆解成本：每任务的 cost/calls/budget/usage%。"""
    return {
        "tasks": cost_manager.breakdown_by_task(),
    }


# ── Models ──

@router.get("/models")
def get_models():
    """返回已注册模型列表 + 各 agent 节点的当前 provider 分配。"""
    return {
        "models": list_models(),
        "nodes": list_nodes(),
    }


class AssignModelBody(BaseModel):
    node: str
    provider: str


@router.put("/models/assign")
def assign_model(body: AssignModelBody):
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
def get_keys():
    """返回所有已配置的 API key（加密遮盖）。"""
    return {"keys": key_store.list_keys()}


class SetKeyBody(BaseModel):
    provider: str
    api_key: str
    base_url: str = ""
    model: str = ""


@router.put("/keys")
def set_key(body: SetKeyBody):
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
def delete_key(body: DeleteKeyBody):
    """删除某个 provider 的 API key 配置。"""
    provider = body.provider.strip().lower()
    ok = key_store.delete_key(provider)
    if not ok:
        return {"ok": False, "error": f"Provider '{provider}' not found."}
    return {"ok": True, "provider": provider}


# ── Prompts ──

@router.get("/prompts")
def get_prompts():
    """返回所有 agent 的当前 prompt 模板。"""
    return {"prompts": prompt_store.list_all()}


class CreatePromptBody(BaseModel):
    agent: str
    system: str
    user_template: str = "{input}"


@router.post("/prompts")
def create_prompt(body: CreatePromptBody):
    """创建新的自定义 prompt 模板。

    Example: POST /admin/prompts
    {"agent": "my_agent", "system": "你是一个...", "user_template": "{input}"}
    """
    ok = prompt_store.add(body.agent.strip(), body.system, body.user_template)
    if not ok:
        return {"ok": False, "error": f"Agent '{body.agent}' already exists or name is empty."}
    return {"ok": True, "agent": body.agent}


class UpdatePromptBody(BaseModel):
    system: str | None = None
    user_template: str | None = None


@router.put("/prompts/{agent}")
def update_prompt(agent: str, body: UpdatePromptBody):
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
def delete_prompt(agent: str):
    """删除指定 agent 的 prompt。
    
    - 自定义 agent：彻底移除
    - 内置 agent：清除覆盖值，恢复默认
    """
    ok = prompt_store.delete(agent)
    if not ok:
        known = [p["agent"] for p in prompt_store.list_all()]
        return {"ok": False, "error": f"Unknown agent '{agent}'. Available: {known}"}
    return {"ok": True, "agent": agent, "message": "Deleted"}


class AIGenerateBody(BaseModel):
    description: str


@router.post("/prompts/ai-generate")
async def ai_generate_prompt(body: AIGenerateBody):
    """使用 AI 根据自然语言描述生成 prompt 模板。

    Example: POST /admin/prompts/ai-generate
    {"description": "一个用于检查 Python 代码风格的 agent"}
    
    Returns {system, user_template, suggested_agent}
    """
    from mix_agent.services.llm import llm_client
    from mix_agent.services.node_config import get_provider

    description = body.description.strip()
    if not description:
        return {"ok": False, "error": "Description is required."}

    provider = get_provider("orchestrator")

    system_instruction = """你是一名 Prompt 工程专家。根据用户的描述，生成一个高质量的 Agent System Prompt 和 User Template。

输出严格的 JSON 格式（不要包含 markdown 代码块标记）：
{
  "system": "system prompt 内容",
  "user_template": "user template，用 {input} 作为输入占位符",
  "suggested_agent": "建议的 agent 标识符（小写+下划线，如 code_style_checker）"
}

要求：
- system prompt 要清晰定义 agent 的角色、输入格式、输出格式和分析维度
- user_template 默认为 "{input}"，如有特殊需要可以定制
- suggested_agent 要简短有意义，能表达 agent 的功能"""

    try:
        response = await llm_client.chat_with_prompt(
            provider=provider,
            system_prompt=system_instruction,
            user_message=f"请为以下需求生成 Agent Prompt：\n\n{description}",
            temperature=0.7,
            max_tokens=2048,
        )

        content = response.content.strip()
        # 提取 JSON：找第一个 { 和最后一个 }
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or start > end:
            return {"ok": False, "error": f"AI response contains no JSON: {content[:500]}"}
        content = content[start:end + 1]

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"AI returned invalid JSON: {content[:500]}"}

        return {
            "ok": True,
            "system": result.get("system", ""),
            "user_template": result.get("user_template", "{input}"),
            "suggested_agent": result.get("suggested_agent", "custom_agent"),
        }

    except Exception as e:
        return {"ok": False, "error": f"AI generation failed: {str(e)}"}


# ── MCP Servers ──

@router.get("/mcp/servers")
def list_mcp_servers():
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
def add_mcp_server(body: AddMCPServerBody):
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
def update_mcp_server(name: str, body: UpdateMCPServerBody):
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
def delete_mcp_server(name: str):
    """删除 MCP 服务器配置。"""
    ok = mcp_store.delete(name)
    if not ok:
        return {"ok": False, "error": f"Server '{name}' not found."}
    return {"ok": True, "name": name}


@router.post("/mcp/servers/{name}/test")
async def test_mcp_server(name: str):
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
