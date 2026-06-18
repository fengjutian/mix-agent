"""管理后台 API — 成本看板、模型配置。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mix_agent.api.deps import require_admin
from mix_agent.services.cost_manager import cost_manager
from mix_agent.services.node_config import list_nodes, list_models, set_node_provider
from mix_agent.services.llm import MODEL_REGISTRY

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
