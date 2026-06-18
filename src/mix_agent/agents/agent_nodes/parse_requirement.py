"""需求解析 Agent — 将模糊自然语言转为结构化扫描任务。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState, TaskStatus
from mix_agent.services.llm import llm_client, CostTracker


_prompts = PromptManager()


async def parse_requirement_node(state: AgentState) -> dict:
    """将用户的模糊需求解析为结构化的审计任务描述。

    使用 MiniMax 进行语义理解，提取 task_name、focus_areas、scope 等。
    """
    prompt = _prompts.get("parse_requirement")

    try:
        resp = await llm_client.chat_with_prompt(
            provider="minimax",
            system_prompt=prompt.system,
            user_message=state.task_description or "请分析代码变更的安全性",
            temperature=0.3,
            max_tokens=1024,
        )

        # 解析 LLM 输出的 JSON
        content = resp.content.strip()
        if content.startswith("```"):
            # 移除 markdown 代码块标记
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        parsed = json.loads(content)
    except Exception:
        # LLM 调用失败时的降级方案
        parsed = {
            "task_name": "自动代码审计",
            "description": state.task_description or "扫描代码变更",
            "focus_areas": ["sql_audit", "code_review", "secret_scan"],
            "scope": "所有变更文件",
            "constraints": [],
        }

    return {
        "task_status": TaskStatus.RUNNING,
        "parse_result": parsed,
        "messages": state.messages,
    }
