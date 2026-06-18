"""LangGraph 状态机图定义 — 注册节点、边缘、安全熔断条件路由。"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from mix_agent.agents.nodes import (
    parse_requirements_node,
    code_analysis_node,
    sql_audit_node,
    summary_node,
    human_approval_node,
)
from mix_agent.schemas import AgentState


def build_graph() -> StateGraph:
    """构建并编译完整的 LangGraph 状态机。"""

    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("parse_requirements", parse_requirements_node)
    workflow.add_node("code_analysis", code_analysis_node)
    workflow.add_node("sql_audit", sql_audit_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("summary", summary_node)

    # 定义边
    workflow.set_entry_point("parse_requirements")
    workflow.add_edge("parse_requirements", "code_analysis")
    workflow.add_edge("code_analysis", "sql_audit")

    # 条件路由：SQL 审计结果触发人工确认还是直接结束
    workflow.add_conditional_edges(
        "sql_audit",
        lambda s: "human_approval" if s.pending_approval else "summary",
        {"human_approval": "human_approval", "summary": "summary"},
    )

    workflow.add_edge("human_approval", "summary")
    workflow.add_edge("summary", END)

    # 编译（使用内存检查点，后续可替换为 Redis 持久化）
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# 单例图实例
agent_graph = build_graph()
