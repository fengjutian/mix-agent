"""智能体总线任务生命周期启停 API — 提交模糊需求，启动状态图。"""

from uuid import uuid4

from fastapi import APIRouter

from mix_agent.schemas import TaskRequest, TaskResponse, TaskStatus

router = APIRouter()


@router.post("/", response_model=TaskResponse)
async def create_task(req: TaskRequest):
    """提交一个新的模糊需求任务，启动 LangGraph 状态机。"""
    task_id = str(uuid4())
    # TODO: 在后台启动 LangGraph 图执行
    return TaskResponse(task_id=task_id, status=TaskStatus.PENDING)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """查询指定任务的当前状态。"""
    # TODO: 从 Redis 中读取任务状态
    return TaskResponse(task_id=task_id, status=TaskStatus.PENDING)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str):
    """取消正在运行的任务。"""
    # TODO: 中断 LangGraph 执行
    return TaskResponse(task_id=task_id, status=TaskStatus.CANCELLED)
