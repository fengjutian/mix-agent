"""Git Review Agent — 基于 Git 历史、diff、blame 的全面代码审查。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.services.prompt_store import prompt_store
from mix_agent.schemas import AgentState
from mix_agent.services.llm import llm_client
from mix_agent.services.node_config import get_provider
from mix_agent.tools.vcs.git_tool import GitTool

_prompts = PromptManager(store=prompt_store)


async def review_node(state: AgentState) -> dict:
    """基于 Git 历史、diff、blame 进行全面代码审查。

    1. 使用 GitTool 获取提交历史和 diff
    2. 对变更文件进行 blame 分析
    3. 构建结构化上下文发送给 LLM 进行语义分析
    """
    repo_path = state.changed_files[0].get("repo_path", ".") if state.changed_files else "."
    target = state.orchestrator_result.get("target_branch") or "HEAD"
    base = state.orchestrator_result.get("base_branch") or "main"
    
    # Fallback: try to infer from task_description or changed_files context
    if repo_path == ".":
        repo_path = (state.parse_result or {}).get("repo_path", ".")
    if not state.orchestrator_result.get("target_branch"):
        # orchestrator_result doesn't carry target/base — read from parse_result or use defaults
        target = (state.parse_result or {}).get("target_branch", "HEAD")
        base = (state.parse_result or {}).get("base_branch", "main")

    git = GitTool(repo_path)

    # ── 1. 获取提交历史 ──
    try:
        commits = git.log(branch=target, max_count=30)
    except Exception:
        commits = []

    # ── 2. 获取 diff ──
    try:
        diff_result = git.diff(target=target, base=base)
    except Exception:
        return {
            "review_result": {
                "summary": "无法获取 Git diff，审查终止",
                "commit_analysis": [],
                "findings": [],
                "risk_summary": {"danger": 0, "warning": 0, "safe": 0},
                "recommendations": [],
            },
        }

    # ── 3. 对变更文件进行 blame 分析（限制前 15 个文件） ──
    blame_data: dict[str, list[dict]] = {}
    py_files = [
        cf.file_path
        for cf in diff_result.changed_files
        if cf.file_path.endswith(".py") and cf.change_type.value != "deleted"
    ]
    for fpath in py_files[:15]:
        try:
            lines = git.blame(fpath, revision=target)
            blame_data[fpath] = [l.to_dict() for l in lines[:200]]  # 限制每文件 200 行
        except Exception:
            blame_data[fpath] = []

    # ── 4. 构建 LLM 上下文 ──
    context_parts: list[str] = []

    # 提交历史摘要
    context_parts.append("=== 提交历史 ===")
    for c in commits[:20]:
        context_parts.append(
            f"  {c.short_sha} | {c.date} | {c.author}\n"
            f"    {c.message}"
        )

    # Diff 摘要
    context_parts.append(f"\n=== 变更统计 ===")
    context_parts.append(f"  总增加: {diff_result.total_additions} 行")
    context_parts.append(f"  总删除: {diff_result.total_deletions} 行")
    context_parts.append(f"  变更文件: {len(diff_result.changed_files)} 个")

    for cf in diff_result.changed_files:
        context_parts.append(
            f"  [{cf.change_type.value}] {cf.file_path} "
            f"(+{cf.additions}/-{cf.deletions})"
        )

    # Diff 内容（截断防止 token 溢出）
    diff_text = diff_result.raw_diff
    if len(diff_text) > 6000:
        diff_text = diff_text[:6000] + "\n... (truncated)"

    context_parts.append(f"\n=== Diff 内容（截断至 6000 字符）===")
    context_parts.append(diff_text)

    # Blame 摘要
    if blame_data:
        context_parts.append(f"\n=== Blame 信息（{len(blame_data)} 个文件）===")
        for fpath, lines in blame_data.items():
            if not lines:
                continue
            authors = list({l["author"] for l in lines if l.get("author")})
            context_parts.append(
                f"  {fpath}: {len(lines)} 行, 作者: {', '.join(authors[:5])}"
            )

    context = "\n".join(context_parts)

    # ── 5. LLM 分析 ──
    if not context.strip():
        return {
            "review_result": {
                "summary": "无变更内容可供审查",
                "commit_analysis": [],
                "findings": [],
                "risk_summary": {"danger": 0, "warning": 0, "safe": 0},
                "recommendations": [],
            },
        }

    prompt = _prompts.get("review")
    try:
        resp = await llm_client.chat_with_prompt(
            provider=get_provider("review"),
            system_prompt=prompt.system,
            user_message=context[:8000],  # 限制总长度
            temperature=0.3,
            max_tokens=3072,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        result = json.loads(content)
    except Exception:
        result = {
            "summary": "LLM 分析暂不可用",
            "commit_analysis": [],
            "findings": [],
            "risk_summary": {"danger": 0, "warning": 0, "safe": 0},
            "recommendations": [],
        }

    return {
        "review_result": result,
    }
