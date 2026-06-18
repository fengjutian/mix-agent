"""汇总报告 Agent — 所有分析结果 → LLM 综合报告（含 RAG 检索增强）。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState, TaskStatus
from mix_agent.services.llm import llm_client
from mix_agent.services.node_config import get_provider

_prompts = PromptManager()


async def summary_node(state: AgentState) -> dict:
    """汇总所有 Agent 输出，生成审计报告。

    Phase 2 增强：
    - 检索历史相似审计结果作为参考上下文 (RAG)
    - 审计完成后将报告摘要向量化存入 Qdrant (knowledge collection)
    """
    # 收集所有节点输出
    task_desc = state.task_description or "代码安全审计"
    changed_summary = ", ".join(
        cf.get("file_path", "") for cf in state.changed_files[:5]
    )

    # ── RAG: 检索历史相似审计 ──
    rag_context = ""
    try:
        from mix_agent.api.deps import get_qdrant
        from mix_agent.services.rag import RAGService

        qdrant = get_qdrant()
        rag = RAGService(qdrant)
        rag_context = rag.find_similar_audits(task_desc)
    except Exception:
        pass  # Qdrant 不可用时跳过

    # 构建 Prompt 上下文
    user_context = {
        "task": task_desc,
        "changed_files": changed_summary,
        "parse_result": state.parse_result,
        "code_review": state.code_review_result,
        "sql_audit": state.sql_audit_result,
        "accumulated_tokens": state.accumulated_tokens,
    }

    # 注入 RAG 上下文
    if rag_context:
        user_context["similar_audits"] = rag_context

    prompt = _prompts.get("summary")
    try:
        resp = await llm_client.chat_with_prompt(
            provider=get_provider("summary"),
            system_prompt=prompt.system,
            user_message=json.dumps(user_context, ensure_ascii=False, default=str)[:4000],
            temperature=0.3,
            max_tokens=2048,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        result = json.loads(content)
    except Exception:
        result = {
            "title": "安全审计报告",
            "summary": f"完成 {len(state.changed_files)} 个文件变更的审计",
            "risk_summary": {"danger": 0, "warning": 0, "safe": 0},
            "findings_by_agent": {},
            "top_recommendations": [],
            "conclusion": "审计完成",
        }

    # ── 审计报告入库 (knowledge collection) ──
    try:
        from mix_agent.api.deps import get_qdrant
        from mix_agent.services.rag import RAGService

        qdrant = get_qdrant()
        rag = RAGService(qdrant)
        report_text = json.dumps(result, ensure_ascii=False)
        rag.ingest(
            texts=[report_text],
            metadata_list=[{
                "type": "audit_report",
                "task_description": task_desc,
                "files": changed_summary,
            }],
        )
    except Exception:
        pass  # 入库失败不影响主流程

    return {
        "summary_result": result,
        "task_status": TaskStatus.COMPLETED,
    }
