"""Phase 2 AI Agent API — 基于 LangGraph 的智能审计流水线。

接收自然语言描述 → Git Diff → parse_requirement → orchestrator → 
code_review → sql_risk_explain → [human_approval] → summary → 报告。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from mix_agent.agents.graph import agent_graph
from mix_agent.api.deps import get_current_user
from mix_agent.api.v1_approvals import register_pending_approval
from mix_agent.schemas import AgentState, AgentRunRequest, AgentRunResponse, TaskStatus
from mix_agent.tools.vcs.git_tool import GitTool

router = APIRouter()

# 内存存储 agent 运行结果
_agent_results: dict[str, dict] = {}


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(req: AgentRunRequest, user: dict = Depends(get_current_user)):
    """启动 AI Agent 审计流水线。

    提交自然语言描述和仓库/分支信息，运行完整的 LangGraph 流水线：
    - parse_requirement: LLM 理解模糊需求
    - orchestrator: 混合路由决定激活哪些 Agent
    - code_review: AST 符号表 + LLM 代码审查
    - sql_risk_explain: SQLGuard + LLM 风险解释
    - human_approval: 高危操作触发人工审批（如需要）
    - summary: LLM 生成综合审计报告

    返回 task_id 和最终状态，可通过 GET /api/v1/agent/{task_id}/result 获取完整结果。
    """
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # ── 1. Git Diff ──
    git = GitTool(req.repo_path)
    try:
        diff_result = git.diff(target=req.target_branch, base=req.base_branch)
        changed_files = [cf.to_dict() for cf in diff_result.changed_files]
    except (ValueError, RuntimeError) as e:
        changed_files = []
        git_error = str(e)
    else:
        git_error = None

    if not changed_files and not req.force:
        raise HTTPException(
            status_code=400,
            detail=f"No file changes detected between {req.base_branch}..{req.target_branch}. "
                   f"Use force=true to run anyway.",
        )

    # ── 2. 构建初始状态 ──
    initial_state = AgentState(
        task_description=req.description or f"审计 {req.base_branch}..{req.target_branch} 的代码变更",
        task_status=TaskStatus.RUNNING,
        changed_files=changed_files,
    )

    # ── 3. 运行 LangGraph ──
    thread_id = task_id
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = await agent_graph.ainvoke(initial_state, config)
    except Exception as e:
        _agent_results[task_id] = {
            "task_id": task_id,
            "status": TaskStatus.FAILED,
            "description": req.description,
            "target_branch": req.target_branch,
            "base_branch": req.base_branch,
            "repo_path": req.repo_path,
            "changed_files_count": len(changed_files),
            "created_at": now,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
            "result": None,
        }
        return AgentRunResponse(
            task_id=task_id,
            status=TaskStatus.FAILED,
            message=f"Agent execution failed: {e}",
        )

    # ── 4. 处理 HiL 审批 ──
    pending = final_state.get("pending_approval")
    if pending is not None:
        pending.task_id = task_id
        register_pending_approval(task_id, pending)

    # ── 5. 存储结果 ──
    _agent_results[task_id] = {
        "task_id": task_id,
        "status": final_state.get("task_status", TaskStatus.COMPLETED),
        "description": req.description,
        "target_branch": req.target_branch,
        "base_branch": req.base_branch,
        "repo_path": req.repo_path,
        "changed_files_count": len(changed_files),
        "created_at": now,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "git_error": git_error,
        "result": {
            "parse_result": final_state.get("parse_result", {}),
            "orchestrator_result": final_state.get("orchestrator_result", {}),
            "code_review_result": final_state.get("code_review_result", {}),
            "sql_audit_result": final_state.get("sql_audit_result", {}),
            "summary_result": final_state.get("summary_result", {}),
            "accumulated_tokens": final_state.get("accumulated_tokens", 0),
        },
        "changed_files": changed_files,
    }

    return AgentRunResponse(
        task_id=task_id,
        status=final_state.get("task_status", TaskStatus.COMPLETED),
        message="Agent audit completed",
    )


@router.get("/{task_id}/result")
async def get_agent_result(task_id: str, user: dict = Depends(get_current_user)):
    """获取 AI Agent 审计的完整结果，包含所有节点的输出。"""
    result = _agent_results.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent result not found")
    return result
