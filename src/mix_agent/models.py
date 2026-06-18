"""PostgreSQL database models (SQLAlchemy ORM).

Uses TypeDecorator adapters to support both PostgreSQL (production) and SQLite (testing).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator, String as SAString


# ── Cross-engine compatible types ──


class UniversalUUID(TypeDecorator):
    """UUID: PostgreSQL native, others fall back to CHAR(36)."""
    impl = SAString(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(SAString(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class UniversalJSONB(TypeDecorator):
    """JSON: PostgreSQL JSONB, others fall back to JSON."""
    impl = JSON()
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class UniversalINET(TypeDecorator):
    """INET: PostgreSQL INET, others fall back to VARCHAR(45)."""
    impl = SAString(45)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(SAString(45))


class Base(DeclarativeBase):
    pass


# ── Users & Teams ──


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="developer")
    team_id: Mapped[uuid.UUID | None] = mapped_column(UniversalUUID(), ForeignKey("teams.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    team: Mapped[Team | None] = relationship("Team", back_populates="users")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    users: Mapped[list[User]] = relationship("User", back_populates="team")


# ── Tasks ──


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), ForeignKey("users.id"), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(UniversalUUID(), ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    repo_path: Mapped[str] = mapped_column(Text, nullable=False)
    target_branch: Mapped[str] = mapped_column(String(256), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(256), nullable=False, default="main")
    path_filter: Mapped[str | None] = mapped_column(String(512))
    task_type: Mapped[str] = mapped_column(String(16), default="standard")
    cost_budget: Mapped[float] = mapped_column(Numeric(8, 4), default=0.05)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    diff_files: Mapped[list[DiffFile]] = relationship("DiffFile", back_populates="task")
    audit_findings: Mapped[list[AuditFinding]] = relationship("AuditFinding", back_populates="task")
    audit_report: Mapped[AuditReport | None] = relationship("AuditReport", back_populates="task", uselist=False)

    __table_args__ = (
        Index("idx_tasks_user", "user_id", "created_at"),
        Index("idx_tasks_team", "team_id", "created_at"),
    )


# ── Diff Files ──


class DiffFile(Base):
    __tablename__ = "diff_files"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)

    task: Mapped[Task] = relationship("Task", back_populates="diff_files")


# ── Audit Findings ──


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text)
    line_number: Mapped[int | None] = mapped_column(Integer)
    code_snippet: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    auto_fix_patch: Mapped[str | None] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    task: Mapped[Task] = relationship("Task", back_populates="audit_findings")

    __table_args__ = (
        Index("idx_findings_task", "task_id"),
    )


# ── Approvals ──


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False)
    auditor_id: Mapped[uuid.UUID | None] = mapped_column(UniversalUUID(), ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ── Audit Reports ──


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UniversalUUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    format: Mapped[str] = mapped_column(String(8), nullable=False, default="json")
    content: Mapped[dict] = mapped_column(UniversalJSONB(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    task: Mapped[Task] = relationship("Task", back_populates="audit_report")


# ── Audit Operation Log ──


class AuditOperationLog(Base):
    __tablename__ = "audit_operation_log"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(UniversalUUID())
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UniversalUUID())
    detail: Mapped[dict | None] = mapped_column(UniversalJSONB())
    ip_address: Mapped[str | None] = mapped_column(UniversalINET())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "created_at"),
    )


# ── LLM Token Logs ──


class AgentTokenLog(Base):
    __tablename__ = "agent_token_logs"

    id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), ForeignKey("tasks.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_token_logs_task", "task_id"),
    )


# ── Global Settings ──


class GlobalSettings(Base):
    """全局应用设置 — 单行配置表，使用 JSONB 存储所有设置项。"""

    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[dict] = mapped_column(UniversalJSONB(), nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ── LangGraph Checkpoints ──


class LangGraphCheckpoint(Base):
    __tablename__ = "langgraph_checkpoints"

    thread_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, nullable=False)
    checkpoint_ns: Mapped[str] = mapped_column(String(256), primary_key=True, nullable=False, default="")
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(UniversalUUID(), primary_key=True, nullable=False)
    parent_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(UniversalUUID())
    type: Mapped[str | None] = mapped_column(String(32))
    checkpoint: Mapped[dict] = mapped_column(UniversalJSONB(), nullable=False)
    checkpoint_metadata: Mapped[dict | None] = mapped_column("metadata", UniversalJSONB())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
