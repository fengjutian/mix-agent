"""人工确认回路（Human-in-the-Loop）二次确认、中断放行专用 API。"""

from fastapi import APIRouter

from mix_agent.schemas import ApprovalAction, ApprovalRequest, TaskStatus

router = APIRouter()


@router.get("/pending/{task_id}", response_model=ApprovalRequest)
async def get_pending_approval(task_id: str):
    """获取当前挂起的人工确认请求详情。"""
    # TODO: 从 LangGraph 挂起状态中读取
    return ApprovalRequest(
        task_id=task_id,
        node_name="unknown",
        prompt="等待人工确认…",
    )


@router.post("/respond", response_model=dict)
async def respond_approval(action: ApprovalAction):
    """提交人工确认/驳回/修改决策，放行中断的状态机。"""
    # TODO: 根据 decision 向 LangGraph 发送 Command(resume=...)
    return {"status": "ok", "task_id": action.task_id, "decision": action.decision.value}
