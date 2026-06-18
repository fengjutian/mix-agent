"""LLM Token 日志服务 — 将每次 LLM 调用的 token 消耗和成本写入数据库。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from mix_agent.models import AgentTokenLog


class TokenLogService:
    """LLM Token 消耗日志服务。

    职责：
    - 记录每次 LLM 调用的 prompt_tokens / completion_tokens / cost
    - 按 task_id / agent / model 聚合查询累计成本
    """

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def record(
        self,
        task_id: str,
        agent: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
    ) -> None:
        """记录一次 LLM 调用。"""
        with self._session_factory() as session:
            log = AgentTokenLog(
                task_id=task_id,
                agent=agent,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost,
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            session.commit()

    def get_task_cost(self, task_id: str) -> dict:
        """获取指定任务的累计成本。"""
        with self._session_factory() as session:
            result = session.execute(
                select(
                    func.sum(AgentTokenLog.prompt_tokens),
                    func.sum(AgentTokenLog.completion_tokens),
                    func.sum(AgentTokenLog.cost),
                    func.count(AgentTokenLog.id),
                ).where(AgentTokenLog.task_id == task_id)
            ).first()

            if result:
                return {
                    "task_id": task_id,
                    "total_prompt_tokens": int(result[0] or 0),
                    "total_completion_tokens": int(result[1] or 0),
                    "total_cost": float(result[2] or 0),
                    "total_calls": int(result[3] or 0),
                }
            return {
                "task_id": task_id,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_cost": 0.0,
                "total_calls": 0,
            }

    def get_agent_breakdown(self, task_id: str) -> list[dict]:
        """按 Agent 拆解成本。"""
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    AgentTokenLog.agent,
                    func.sum(AgentTokenLog.cost).label("cost"),
                    func.count(AgentTokenLog.id).label("calls"),
                )
                .where(AgentTokenLog.task_id == task_id)
                .group_by(AgentTokenLog.agent)
            ).all()

            return [
                {"agent": row.agent, "cost": float(row.cost), "calls": row.calls}
                for row in rows
            ]
