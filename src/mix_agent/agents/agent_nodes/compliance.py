"""合规检查 Agent — YAML 规则引擎 + LLM 解释违规。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.services.prompt_store import prompt_store
from mix_agent.schemas import AgentState
from mix_agent.services.llm import llm_client
from mix_agent.services.node_config import get_provider
from mix_agent.tools.security.compliance_checker import ComplianceChecker

_prompts = PromptManager(store=prompt_store)
_prompts.register("compliance", type(_prompts.get("summary"))(
    agent="compliance",
    system="""你是一名合规审计专家。审核合规扫描结果并提供整改建议。

输入：合规扫描发现的违规列表（含 rule_id, category, severity, evidence）。

输出 JSON：
{
  "findings": [
    {
      "rule": "OWASP-A01",
      "severity": "danger",
      "explanation": "详细解释为什么是违规",
      "remediation": "具体的修复步骤",
      "reference": "OWASP 参考链接"
    }
  ],
  "summary": "合规审计总结"
}
"""
))


async def compliance_node(state: AgentState) -> dict:
    """合规检查节点。

    1. 运行 ComplianceChecker 扫描变更文件
    2. LLM 补充解释违规并给出整改建议
    """
    changed_files = [
        cf["file_path"] for cf in state.changed_files
        if cf.get("change_type") != "deleted"
    ]

    if not changed_files:
        return {"compliance_result": {"violations": [], "summary": "无变更文件"}}

    checker = ComplianceChecker()
    result = checker.scan_files(changed_files)

    violations_data = [
        {
            "rule": v.rule_id,
            "category": v.category,
            "severity": v.severity,
            "description": v.description,
            "file": v.file_path,
            "evidence": v.evidence,
        }
        for v in result.violations
    ]

    if not violations_data:
        return {
            "compliance_result": {
                "violations": [],
                "by_category": {},
                "by_severity": {},
                "summary": f"扫描 {result.files_scanned} 个文件，{result.rules_checked} 条规则，未发现违规",
            },
        }

    # LLM 分析
    llm_findings: list[dict] = []
    try:
        resp = await llm_client.chat_with_prompt(
            provider=get_provider("compliance"),
            system_prompt=_prompts.get("compliance").system,
            user_message=json.dumps(violations_data[:20], ensure_ascii=False),
            temperature=0.2,
            max_tokens=2048,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        llm_result = json.loads(content)
        llm_findings = llm_result.get("findings", [])
    except Exception:
        llm_findings = violations_data

    return {
        "compliance_result": {
            "violations": violations_data,
            "llm_findings": llm_findings,
            "by_category": result.by_category,
            "by_severity": result.by_severity,
            "summary": f"发现 {len(violations_data)} 项违规 ({len(result.by_severity)} 个类别)",
        },
    }
