"""A2A 消息封包、状态通道（LangGraph Channels）强类型定义。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ──────────── A2A 消息协议 ────────────


class Role(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class A2AMessage(BaseModel):
    """A2A 协议消息封包。"""

    role: Role
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ──────────── 任务生命周期 ────────────


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRequest(BaseModel):
    """用户提交的任务请求（Phase 1：指定仓库和分支）。"""

    description: str = ""
    target_branch: str = "HEAD"
    base_branch: str = "main"
    repo_path: str = "."
    context: dict[str, Any] = Field(default_factory=dict)


class TaskDetail(BaseModel):
    """任务详情响应。"""

    task_id: str
    status: TaskStatus
    description: str = ""
    target_branch: str = "HEAD"
    base_branch: str = "main"
    repo_path: str = "."
    created_at: str | None = None
    completed_at: str | None = None


class TaskResponse(BaseModel):
    """任务创建响应。"""

    task_id: str
    status: TaskStatus


# ──────────── Phase 2 AI Agent ────────────


class AgentRunRequest(BaseModel):
    """AI Agent 审计请求（LLM 理解 + 编排）。"""

    description: str = ""
    target_branch: str = "HEAD"
    base_branch: str = "main"
    repo_path: str = "."
    force: bool = False  # 即使无变更也强制运行


class AgentRunResponse(BaseModel):
    """AI Agent 审计响应。"""

    task_id: str
    status: TaskStatus
    message: str = ""


# ──────────── 审计发现与报告 ────────────


class FindingItem(BaseModel):
    """单条审计发现。"""

    agent: str  # sql_audit / secret_scanner / ast_analyzer / git_diff
    finding_type: str
    risk_level: str  # safe / warning / danger
    file_path: str | None = None
    line_number: int | None = None
    code_snippet: str | None = None
    description: str = ""
    recommendation: str = ""


class FindingsResponse(BaseModel):
    """发现项列表响应。"""

    task_id: str
    findings: list[FindingItem] = Field(default_factory=list)
    total: int = 0


class ReportResponse(BaseModel):
    """审计报告响应。"""

    task_id: str
    format: str = "json"
    summary: str = ""
    total_findings: int = 0
    danger_count: int = 0
    warning_count: int = 0
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[FindingItem] = Field(default_factory=list)
    ast_symbols: dict[str, Any] = Field(default_factory=dict)


# ──────────── 人工确认回路 ────────────


class ApprovalRequest(BaseModel):
    """挂起的中断，等待人工确认。"""

    task_id: str
    node_name: str
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"


class ApprovalAction(BaseModel):
    """人工确认操作。"""

    task_id: str
    decision: ApprovalDecision
    feedback: str = ""
    modified_payload: dict[str, Any] | None = None


# ──────────── LangGraph 状态通道 ────────────


class AgentState(BaseModel):
    """LangGraph 状态机通道定义。"""

    messages: list[A2AMessage] = Field(default_factory=list)
    task_description: str = ""
    task_status: TaskStatus = TaskStatus.PENDING
    pending_approval: ApprovalRequest | None = None
    accumulated_tokens: int = 0
    error: str | None = None

    # ── 节点输出 ──
    parse_result: dict[str, Any] = Field(default_factory=dict)
    orchestrator_result: dict[str, Any] = Field(default_factory=dict)
    code_review_result: dict[str, Any] = Field(default_factory=dict)
    sql_audit_result: dict[str, Any] = Field(default_factory=dict)
    auto_fix_result: dict[str, Any] = Field(default_factory=dict)
    summary_result: dict[str, Any] = Field(default_factory=dict)

    # Phase 1 工具数据
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    ast_symbols: dict[str, Any] = Field(default_factory=dict)
