"""编排 Agent — 混合路由：确定性规则强制激活 + LLM 语义补充。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState, TaskStatus
from mix_agent.services.llm import llm_client

_prompts = PromptManager()

# 确定性规则：文件扩展名 → 强制激活的 Agent
RULE_MAP = {
    ".sql": ["sql_audit"],
    ".py": ["code_review"],
    "pyproject.toml": ["dependency_audit"],
    "package.json": ["dependency_audit"],
    "requirements.txt": ["dependency_audit"],
    ".env": ["config_audit"],
    ".yaml": ["config_audit"],
    ".yml": ["config_audit"],
    "settings.py": ["config_audit"],
    "config.py": ["config_audit"],
}


async def orchestrator_node(state: AgentState) -> dict:
    """混合路由编排器。

    1. 确定性规则引擎：基于变更文件扩展名强制激活对应 Agent
    2. LLM 语义补充：解析 parse_result 中的 focus_areas，补充激活
    """
    activated: set[str] = set()

    # 1. 规则引擎强制激活
    for cf in state.changed_files:
        path = cf.get("file_path", "")
        for pattern, agents in RULE_MAP.items():
            if path.endswith(pattern):
                activated.update(agents)

    # 2. LLM 语义补充
    parse_result = state.parse_result or {}
    focus_areas = parse_result.get("focus_areas", [])
    activated.update(focus_areas)

    # 永远激活 secret_scan（无 LLM 成本）
    activated.add("secret_scan")

    # 3. 可选：LLM 进一步分析（仅在规则不够时）
    reasoning = "规则引擎 + focus_areas 激活"
    if not activated:
        prompt = _prompts.get("orchestrator")
        try:
            resp = await llm_client.chat_with_prompt(
                provider="deepseek",
                system_prompt=prompt.system,
                user_message=json.dumps({
                    "parse_result": parse_result,
                    "changed_files": state.changed_files,
                }, ensure_ascii=False),
                temperature=0.2,
                max_tokens=512,
            )
            llm_result = json.loads(resp.content.strip().lstrip("```json").rstrip("```"))
            activated.update(llm_result.get("activated_agents", []))
            reasoning = llm_result.get("reasoning", reasoning)
        except Exception:
            pass

    result = {
        "activated_agents": sorted(activated),
        "reasoning": reasoning,
        "priority_order": sorted(activated),  # 简化为字母序
    }

    return {
        "orchestrator_result": result,
    }
