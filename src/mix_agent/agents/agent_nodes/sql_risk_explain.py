"""SQL 风险解释 Agent — 规则命中 → LLM 解读 + HiL 中断。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState, ApprovalRequest, TaskStatus
from mix_agent.services.llm import llm_client
from mix_agent.tools.security.sql_guard import SQLGuard, RiskLevel

_prompts = PromptManager()


async def sql_risk_explain_node(state: AgentState) -> dict:
    """SQL 审计 + 风险解释 + 高危操作 HiL 中断。

    1. 调用 SQLGuard 对变更的 SQL 文件进行审计
    2. 对高风险 SQL 调用 LLM 解读
    3. 发现 danger 级别操作时设置 pending_approval（图的条件路由会导向 human_approval）
    """
    # 1. 收集 SQL 文件和语句
    sql_files = [
        cf["file_path"]
        for cf in state.changed_files
        if cf.get("file_path", "").endswith(".sql")
        and cf.get("change_type") != "deleted"
    ]

    guard = SQLGuard()
    all_results: list[dict] = []

    for fp in sql_files:
        try:
            with open(fp, encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue

        statements = [s.strip() for s in content.split(";") if s.strip()]
        for stmt in statements:
            result = guard.audit(stmt)
            all_results.append({
                "sql": stmt[:200],
                "file": fp,
                "risk_level": result.risk_level.value,
                "reasons": result.reasons,
                "is_blocked": result.is_blocked,
            })

    if not all_results:
        return {"sql_audit_result": {"findings": [], "needs_approval": False}}

    # 2. LLM 解读高风险 SQL
    danger_items = [r for r in all_results if r["risk_level"] == "danger"]
    llm_explanation = {"explanations": []}
    if danger_items:
        try:
            resp = await llm_client.chat_with_prompt(
                provider="deepseek",
                system_prompt=_prompts.get("sql_risk_explain").system,
                user_message=json.dumps({"audit_results": danger_items}, ensure_ascii=False),
                temperature=0.2,
                max_tokens=1024,
            )
            content = resp.content.strip().lstrip("```json").rstrip("```")
            llm_explanation = json.loads(content)
        except Exception:
            pass

    # 3. 设置是否需审批
    needs_approval = len(danger_items) > 0
    pending = None
    if needs_approval:
        pending = ApprovalRequest(
            task_id="",
            node_name="sql_risk_explain",
            prompt=f"发现 {len(danger_items)} 个高危 SQL 操作，需要人工审批",
            context={
                "danger_count": len(danger_items),
                "items": danger_items,
            },
        )

    return {
        "sql_audit_result": {
            "findings": all_results,
            "llm_explanation": llm_explanation,
            "needs_approval": needs_approval,
        },
        "pending_approval": pending,
        "task_status": TaskStatus.AWAITING_APPROVAL if needs_approval else state.task_status,
    }
