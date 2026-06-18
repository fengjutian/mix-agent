"""审批流 API — Human-in-the-Loop 待审批列表与决策提交。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from mix_agent.schemas import ApprovalAction, ApprovalDecision, ApprovalRequest, TaskStatus

router = APIRouter()

# ── 模拟审批存储（生产环境替换为 PostgreSQL） ──

_pending_approvals: dict[str, ApprovalRequest] = {}
_audit_log: list[dict] = []


# ── 公共接口 ──


@router.get("/pending")
def list_pending_approvals():
    """获取当前所有待审批项（需 auditor 或 admin 角色）。"""
    items = [
        {
            "task_id": task_id,
            "node_name": ar.node_name,
            "prompt": ar.prompt,
            "risk_summary": ar.context.get("danger_count", 0) if ar.context else 0,
        }
        for task_id, ar in _pending_approvals.items()
    ]
    return {"items": items, "total": len(items)}


@router.get("/pending/{task_id}")
def get_pending_approval(
    task_id: str,
):
    """获取指定任务的待审批详情。"""
    ar = _pending_approvals.get(task_id)
    if ar is None:
        raise HTTPException(status_code=404, detail="No pending approval for this task")
    return ar


@router.post("/respond")
def respond_approval(
    action: ApprovalAction,
):
    """提交审批决策（approve / reject / modify）。

    审批通过后从待审批列表移除，外部应恢复 LangGraph 状态机继续执行。
    """
    task_id = action.task_id

    if task_id not in _pending_approvals:
        raise HTTPException(status_code=404, detail="No pending approval for this task")

    ar = _pending_approvals.pop(task_id)

    # 记录审计日志
    _audit_log.append({
        "task_id": task_id,
        "auditor": user.get("username"),
        "role": user.get("role"),
        "decision": action.decision.value,
        "feedback": action.feedback,
    })

    return {
        "status": "ok",
        "task_id": task_id,
        "decision": action.decision.value,
        "message": f"Approval {action.decision.value} by {user.get('username')}",
    }


# ── 内部接口（供 Agent 节点调用） ──


def register_pending_approval(task_id: str, approval: ApprovalRequest) -> None:
    """注册一个待审批项（由 Agent 节点在发现高危操作时调用）。"""
    approval.task_id = task_id
    _pending_approvals[task_id] = approval


def resolve_pending_approval(task_id: str) -> ApprovalRequest | None:
    """获取并移除待审批项（审批通过后调用）。"""
    return _pending_approvals.pop(task_id, None)
