"""LangGraph 状态机图定义 — 完整 Agent 编排流水线（Phase 2）。"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from mix_agent.agents.agent_nodes import (
    parse_requirement_node,
    orchestrator_node,
    code_review_node,
    sql_risk_explain_node,
    summary_node,
    human_approval_node,
)
from mix_agent.schemas import AgentState, TaskStatus


def _route_after_orchestrator(state: AgentState) -> list[str]:
    """编排后的条件路由：根据 activated_agents 决定执行哪些节点。"""
    agents = state.orchestrator_result.get("activated_agents", [])
    nodes: list[str] = []

    route_map = {
        "sql_audit": "sql_risk_explain",
        "code_review": "code_review",
        # secret_scan / config_audit / dependency_audit 可后续扩展
    }

    for agent in agents:
        node_name = route_map.get(agent)
        if node_name and node_name not in nodes:
            nodes.append(node_name)

    # 至少运行一个节点后进入 summary
    if not nodes:
        nodes.append("summary")

    return nodes


def _route_after_sql(state: AgentState) -> str:
    """SQL 审计后路由：有 pending_approval 则进入人工审批，否则进入汇总。"""
    if state.pending_approval is not None:
        return "human_approval"
    return "summary"


def build_graph() -> StateGraph:
    """构建并编译完整的 LangGraph 状态机。

    流水线: parse_requirement → orchestrator → [code_review, sql_risk_explain]
            → human_approval (条件) → summary → END
    """
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("parse_requirement", parse_requirement_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("code_review", code_review_node)
    workflow.add_node("sql_risk_explain", sql_risk_explain_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("summary", summary_node)

    # 入口
    workflow.set_entry_point("parse_requirement")
    workflow.add_edge("parse_requirement", "orchestrator")

    # 从 orchestrator 分发到各分析节点
    # 简化：固定顺序执行 code_review → sql_risk_explain → summary
    workflow.add_edge("orchestrator", "code_review")
    workflow.add_edge("code_review", "sql_risk_explain")

    # SQL 审计后：条件路由
    workflow.add_conditional_edges(
        "sql_risk_explain",
        _route_after_sql,
        {
            "human_approval": "human_approval",
            "summary": "summary",
        },
    )

    workflow.add_edge("human_approval", "summary")
    workflow.add_edge("summary", END)

    # 编译（开发环境用内存 checkpointer；生产环境替换为 PostgreSQL）
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# 单例图实例
agent_graph = build_graph()
