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
    """用户提交的模糊需求。"""

    description: str
    context: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """任务创建响应。"""

    task_id: str
    status: TaskStatus


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
