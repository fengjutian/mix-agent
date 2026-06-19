"""LangGraph 状态机图定义 — 完整 Agent 编排流水线（Phase 2）。

流水线: parse_requirement → orchestrator → code_review → sql_risk_explain
        → auto_fix → summary → END

orchestrator 之后的条件路由：
  - 如果激活了 review 且未激活 code_review → 走 review 分支
  - 否则 → 走 code_review 分支（默认，硬边完成完整流水线）
  - 如果什么都没激活 → 直接 summary
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from mix_agent.agents.agent_nodes import (
    parse_requirement_node,
    orchestrator_node,
    code_review_node,
    sql_risk_explain_node,
    auto_fix_node,
    summary_node,
    review_node,
)
from mix_agent.schemas import AgentState


def _route_after_orchestrator(state: AgentState) -> str:
    """条件路由：根据 activated_agents 决定下一个节点。

    返回单个节点名（LangGraph 条件边要求返回 str）。
    实际执行顺序由硬边保证：
      code_review → sql_risk_explain → auto_fix → summary → END
      review → summary → END
    """
    agents = state.orchestrator_result.get("activated_agents", [])

    has_code_review = "code_review" in agents
    has_sql_audit = "sql_audit" in agents
    has_review = "review" in agents

    if has_review and not has_code_review and not has_sql_audit:
        return "review"

    if has_code_review or has_sql_audit:
        return "code_review"

    # 无需要 LLM 分析的 agent → 直接 summary
    return "summary"


def build_graph() -> StateGraph:
    """构建并编译完整的 LangGraph 状态机。

    流水线:
      parse_requirement → orchestrator
        ├─→ code_review → sql_risk_explain → auto_fix → summary → END
        ├─→ review → summary → END
        └─→ summary → END
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("parse_requirement", parse_requirement_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("code_review", code_review_node)
    workflow.add_node("sql_risk_explain", sql_risk_explain_node)
    workflow.add_node("auto_fix", auto_fix_node)
    workflow.add_node("review", review_node)
    workflow.add_node("summary", summary_node)

    # 入口
    workflow.set_entry_point("parse_requirement")
    workflow.add_edge("parse_requirement", "orchestrator")

    # 条件路由：orchestrator → code_review | review | summary
    workflow.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {
            "code_review": "code_review",
            "review": "review",
            "summary": "summary",
        },
    )

    # 硬边定义顺序流水线
    workflow.add_edge("code_review", "sql_risk_explain")
    workflow.add_edge("sql_risk_explain", "auto_fix")
    workflow.add_edge("auto_fix", "summary")
    workflow.add_edge("review", "summary")
    workflow.add_edge("summary", END)

    # 编译
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# 单例图实例
agent_graph = build_graph()
