"""任务生命周期 API — Phase 1 确定性扫描流水线。"""

from fastapi import APIRouter, HTTPException, Query

from mix_agent.schemas import (
    FindingsResponse,
    ReportResponse,
    TaskDetail,
    TaskRequest,
    TaskResponse,
    TaskStatus,
)
from mix_agent.services.task_service import task_service

router = APIRouter()


@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(req: TaskRequest):
    """创建并执行审计任务。

    提交仓库路径和目标/基准分支，立即运行 Git Diff → AST 分析 → SQL 审计 → 密钥扫描流水线。
    """
    task = task_service.create_task(
        description=req.description,
        target_branch=req.target_branch,
        base_branch=req.base_branch,
        repo_path=req.repo_path,
    )
    return TaskResponse(task_id=task.task_id, status=task.status)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str):
    """查询任务状态与详情。"""
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/findings", response_model=FindingsResponse)
def get_findings(task_id: str):
    """查询任务的所有审计发现项。"""
    findings = task_service.get_findings(task_id)
    if findings is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return findings


@router.get("/{task_id}/report", response_model=ReportResponse)
def get_report(task_id: str, format: str = Query("json", pattern="^(json|md)$")):
    """获取审计报告（JSON 或 Markdown 格式）。

    - format=json: 结构化 JSON 报告
    - format=md: Markdown 文本报告
    """
    report = task_service.get_report(task_id, fmt=format)
    if report is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return report


@router.post("/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str):
    """取消正在运行或等待中的任务。"""
    task = task_service.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(task_id=task.task_id, status=task.status)
