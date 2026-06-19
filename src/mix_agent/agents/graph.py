"""LangGraph 状态机图定义 — 完整 Agent 编排流水线（Phase 2）。"""

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


def _route_after_orchestrator(state: AgentState) -> list[str]:
    """编排后的条件路由：根据 activated_agents 决定执行哪些节点。"""
    agents = state.orchestrator_result.get("activated_agents", [])
    nodes: list[str] = []

    route_map = {
        "sql_audit": "sql_risk_explain",
        "code_review": "code_review",
        "review": "review",
        "secret_scan": "summary",       # 无专用 LLM 节点，规则引擎已覆盖
        "dependency_audit": "summary",  # 无专用节点，记录后跳过
        "config_audit": "summary",      # 无专用节点，记录后跳过
    }

    for agent in agents:
        node_name = route_map.get(agent)
        if node_name and node_name not in nodes:
            nodes.append(node_name)

    # 至少运行一个节点后进入 summary
    if not nodes:
        nodes.append("summary")

    return nodes


def build_graph() -> StateGraph:
    """构建并编译完整的 LangGraph 状态机。

    流水线: parse_requirement → orchestrator → code_review → sql_risk_explain
            → auto_fix → summary → END
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

    # 从 orchestrator 分发到各分析节点
    # 支持条件路由：orchestrator 决定激活哪些 agent
    workflow.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {
            "code_review": "code_review",
            "sql_risk_explain": "sql_risk_explain",
            "review": "review",
            "summary": "summary",
        },
    )

    # review 节点结束后进入 summary
    workflow.add_edge("review", "summary")

    # code_review 完成后进入 sql_risk_explain
    workflow.add_edge("code_review", "sql_risk_explain")

    # SQL 审计后直接进入 auto_fix（审批流程已禁用）
    workflow.add_edge("sql_risk_explain", "auto_fix")

    workflow.add_edge("auto_fix", "summary")
    workflow.add_edge("summary", END)

    # 编译（开发环境用内存 checkpointer；生产环境替换为 PostgreSQL）
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# 单例图实例
agent_graph = build_graph()
