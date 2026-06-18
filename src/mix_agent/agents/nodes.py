"""各个独立异构智能体的具体执行节点实现（核心 Prompt 隔离与 Token 节流点）。"""

from langgraph.types import Command
from typing_extensions import Literal

from mix_agent.schemas import AgentState, ApprovalRequest, TaskStatus


def parse_requirements_node(state: AgentState) -> dict:
    """节点：需求解析 —— 将用户的模糊自然语言转为结构化任务描述。"""
    # TODO: 调用 LLM 进行语义解析
    return {
        "task_status": TaskStatus.RUNNING,
        "messages": state.messages,
    }


def code_analysis_node(state: AgentState) -> dict:
    """节点：代码分析 —— 调用 Tree-sitter AST 解析器提取符号与业务摘要。"""
    # TODO: 调用 ast_analyzer 模块
    return {}


def sql_audit_node(state: AgentState) -> dict:
    """节点：SQL 审计 —— 对提取出的 SQL 语句执行安全门禁检查。"""
    # TODO: 调用 sql_guard 模块
    return {}


def human_approval_node(state: AgentState) -> Command[Literal["summary"]]:
    """节点：人工确认回路 —— 挂起等待审批，中断放行后继续。"""
    state.pending_approval = ApprovalRequest(
        task_id="",
        node_name="human_approval",
        prompt="请确认是否放行以下 SQL 执行？",
    )
    state.task_status = TaskStatus.AWAITING_APPROVAL
    # 中断点：等待外部 API 调用 Command(resume=...) 恢复
    return Command(goto="summary", update={"task_status": TaskStatus.AWAITING_APPROVAL})


def summary_node(state: AgentState) -> dict:
    """节点：汇总输出 —— 生成最终分析报告。"""
    return {
        "task_status": TaskStatus.COMPLETED,
    }
