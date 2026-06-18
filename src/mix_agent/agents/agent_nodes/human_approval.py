"""人工审批节点 — HiL 中断等待管理员审批后恢复。"""

from __future__ import annotations

from mix_agent.schemas import AgentState, ApprovalRequest, TaskStatus


def human_approval_node(state: AgentState) -> dict:
    """人工确认回路 — 保持 AWAITING_APPROVAL 状态。

    外部通过 POST /api/v1/approvals/respond 提交决策后，
    重新 invoke 状态机继续执行。
    """
    if state.pending_approval is None:
        state.pending_approval = ApprovalRequest(
            task_id="",
            node_name="human_approval",
            prompt="请确认是否放行高危操作？",
        )

    return {
        "task_status": TaskStatus.AWAITING_APPROVAL,
        "pending_approval": state.pending_approval,
    }
