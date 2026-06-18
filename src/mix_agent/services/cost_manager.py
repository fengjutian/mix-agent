"""成本管理服务 — 实时累计成本、预算检查与降级策略。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from mix_agent.services.llm import CostTracker


@dataclass
class CostBudget:
    """成本预算配置。"""
    task_id: str
    budget: float  # 任务总预算（USD）
    tracker: CostTracker = field(default_factory=CostTracker)

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget - self.tracker.total_cost)

    @property
    def usage_ratio(self) -> float:
        if self.budget <= 0:
            return 1.0
        return self.tracker.total_cost / self.budget

    @property
    def is_over_budget(self) -> bool:
        return self.tracker.total_cost >= self.budget

    @property
    def needs_downgrade(self) -> bool:
        """达到 80% 预算时降级 (更小/更便宜模型)。"""
        return self.usage_ratio >= 0.8

    @property
    def needs_warning(self) -> bool:
        """达到 50% 预算时警告。"""
        return self.usage_ratio >= 0.5


class CostManager:
    """全局成本管理器。

    职责：
    - 跟踪每个任务的实时成本
    - 预算超限时触发降级策略
    - 提供成本看板数据
    """

    # 模型降级链（高成本 → 低成本）
    DOWNGRADE_CHAIN: dict[str, str] = {
        "minimax": "deepseek",           # MiniMax → DeepSeek（更便宜）
        "deepseek": None,                # DeepSeek 已是最低成本
    }

    def __init__(self):
        self._budgets: dict[str, CostBudget] = {}

    # ── 预算管理 ──

    def create_budget(self, task_id: str, budget: float = 0.05) -> CostBudget:
        """为任务创建成本预算追踪器。"""
        cb = CostBudget(task_id=task_id, budget=budget)
        self._budgets[task_id] = cb
        return cb

    def get_budget(self, task_id: str) -> CostBudget | None:
        return self._budgets.get(task_id)

    def record_cost(
        self,
        task_id: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
    ) -> None:
        """记录一次 LLM 调用成本。"""
        cb = self._budgets.get(task_id)
        if cb:
            cb.tracker.total_prompt_tokens += prompt_tokens
            cb.tracker.total_completion_tokens += completion_tokens
            cb.tracker.total_cost += cost
            cb.tracker.calls += 1

    # ── 降级策略 ──

    def check_downgrade(self, task_id: str, current_provider: str) -> str | None:
        """检查是否需要降级模型。返回降级后的 provider，不需要降级返回 None。"""
        cb = self._budgets.get(task_id)
        if cb is None or not cb.needs_downgrade:
            return None

        downgrade_to = self.DOWNGRADE_CHAIN.get(current_provider)
        if downgrade_to is None:
            return None  # 已是最低成本模型，无法降级

        return downgrade_to

    def get_safe_provider(self, task_id: str, preferred: str = "minimax") -> str:
        """获取安全的 provider（考虑预算降级）。"""
        cb = self._budgets.get(task_id)
        if cb is None:
            return preferred

        if cb.needs_downgrade:
            downgrade = self.DOWNGRADE_CHAIN.get(preferred)
            if downgrade:
                return downgrade

        if cb.is_over_budget:
            # 超预算：强制使用最便宜模型
            return "deepseek"

        return preferred

    # ── 看板数据 ──

    def overview(self) -> dict:
        """成本概览：所有任务的总成本。"""
        total_cost = sum(cb.tracker.total_cost for cb in self._budgets.values())
        total_calls = sum(cb.tracker.calls for cb in self._budgets.values())
        total_prompt = sum(cb.tracker.total_prompt_tokens for cb in self._budgets.values())
        total_completion = sum(cb.tracker.total_completion_tokens for cb in self._budgets.values())
        active_tasks = sum(1 for cb in self._budgets.values() if cb.tracker.calls > 0)

        return {
            "total_cost": round(total_cost, 6),
            "total_calls": total_calls,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "active_tasks": active_tasks,
            "total_tasks": len(self._budgets),
        }

    def breakdown_by_task(self) -> list[dict]:
        """按任务拆解成本。"""
        return [
            {
                "task_id": cb.task_id,
                "cost": round(cb.tracker.total_cost, 6),
                "calls": cb.tracker.calls,
                "budget": cb.budget,
                "usage_pct": round(cb.usage_ratio * 100, 1),
                "needs_downgrade": cb.needs_downgrade,
                "is_over_budget": cb.is_over_budget,
            }
            for cb in self._budgets.values()
        ]


# 单例
cost_manager = CostManager()
