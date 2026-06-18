"""代码 Review Agent — AST 符号表 → LLM 语义审查。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState
from mix_agent.services.llm import llm_client
from mix_agent.tools.parser.ast_analyzer import ASTAnalyzer

_prompts = PromptManager()


async def code_review_node(state: AgentState) -> dict:
    """基于 AST 符号表进行 LLM 语义代码审查。

    1. 调用 ASTAnalyzer 提取变更文件的符号表
    2. 将符号摘要（不送源码）发送给 LLM 进行语义分析
    """
    # 1. 提取符号表
    py_files = [
        cf["file_path"]
        for cf in state.changed_files
        if cf.get("file_path", "").endswith(".py")
        and cf.get("change_type") != "deleted"
    ]

    if not py_files:
        return {
            "code_review_result": {
                "findings": [],
                "overall_assessment": "无 Python 文件变更，跳过代码审查",
            },
        }

    ana = ASTAnalyzer()
    ast_data = ana.parse_files(py_files)

    # 2. 构建符号摘要
    summaries: list[str] = []
    for file_key, symbols in ast_data.get("files", {}).items():
        class_names = [c["name"] for c in symbols.get("classes", [])]
        func_names = [f["name"] for f in symbols.get("functions", [])]
        import_mods = list({i.get("module", "") for i in symbols.get("imports", []) if i.get("module")})

        summary_parts = [f"文件: {file_key}"]
        if class_names:
            summary_parts.append(f"类: {', '.join(class_names)}")
        if func_names:
            summary_parts.append(f"函数: {', '.join(func_names)}")
        if import_mods:
            summary_parts.append(f"关键导入: {', '.join(import_mods[:8])}")
        summaries.append("\n".join(summary_parts))

    symbol_summary = "\n\n".join(summaries)

    # 3. LLM 分析
    if not symbol_summary.strip():
        return {
            "code_review_result": {"findings": [], "overall_assessment": "符号表为空"},
        }

    prompt = _prompts.get("code_review")
    try:
        resp = await llm_client.chat_with_prompt(
            provider="deepseek",
            system_prompt=prompt.system,
            user_message=f"以下是变更文件的符号表摘要：\n\n{symbol_summary[:3000]}",
            temperature=0.3,
            max_tokens=2048,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        result = json.loads(content)
    except Exception:
        result = {
            "findings": [],
            "overall_assessment": "LLM 分析暂不可用",
        }

    return {
        "code_review_result": result,
        "ast_symbols": ast_data.get("files", {}),
    }
