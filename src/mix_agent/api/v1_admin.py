"""管理后台 API — 成本看板、模型配置。"""

from fastapi import APIRouter, Depends

from mix_agent.api.deps import require_admin
from mix_agent.services.cost_manager import cost_manager

router = APIRouter()


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
