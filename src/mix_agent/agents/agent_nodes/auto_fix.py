"""AutoFix Agent — LLM 生成修复 diff，Docker 沙箱验证修复。"""

from __future__ import annotations

import json
import os
import tempfile

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState
from mix_agent.services.llm import llm_client
from mix_agent.services.node_config import get_provider

_prompts = PromptManager()
_prompts.register("auto_fix", type(_prompts.get("code_review"))(
    agent="auto_fix",
    system="""你是一名代码修复专家。基于审计发现的安全问题，生成具体的代码修复方案。

输入：审计发现列表（含文件路径、行号、问题描述、风险等级）
输出：每项发现给出一个修复 patch

输出 JSON：
{
  "fixes": [
    {
      "finding_id": "对应的发现项索引",
      "file": "文件路径",
      "line_start": 行号,
      "description": "修复说明",
      "original_snippet": "原始代码片段",
      "fixed_snippet": "修复后的代码片段",
      "diff": "unified diff 格式的差异",
      "can_auto_apply": true/false
    }
  ]
}
"""
))


async def auto_fix_node(state: AgentState) -> dict:
    """AutoFix 节点。

    1. 收集所有 agent 的 danger/warning 发现项
    2. LLM 生成修复 patch
    3. Docker 沙箱验证修复（编译/测试）
    """
    all_findings: list[dict] = []

    # 从各节点结果收集发现项
    for result_key in ["code_review_result", "sql_audit_result", "api_path_result", "compliance_result"]:
        result = getattr(state, result_key, {}) or {}
        items = result.get("findings", []) or result.get("violations", [])
        for item in items:
            if isinstance(item, dict) and item.get("severity") in ("danger", "warning"):
                all_findings.append(item)

    if not all_findings:
        return {"auto_fix_result": {"fixes": [], "summary": "无需要修复的高危发现"}}

    # LLM 生成修复
    prompt = _prompts.get("auto_fix")
    fixes: list[dict] = []
    try:
        resp = await llm_client.chat_with_prompt(
            provider=get_provider("auto_fix"),
            system_prompt=prompt.system,
            user_message=json.dumps(all_findings[:10], ensure_ascii=False, default=str),
            temperature=0.2,
            max_tokens=4096,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        result = json.loads(content)
        fixes = result.get("fixes", [])
    except Exception:
        # 降级：生成简单补丁
        for i, finding in enumerate(all_findings[:5]):
            if finding.get("file_path"):
                fixes.append({
                    "finding_id": str(i),
                    "file": finding.get("file_path", ""),
                    "description": finding.get("description", ""),
                    "can_auto_apply": False,
                    "reason": "LLM 不可用，需人工审查",
                })

    # Docker 沙箱验证（可选）
    verified_fixes: list[dict] = []
    for fix in fixes:
        if fix.get("can_auto_apply") and fix.get("fixed_snippet"):
            verified = await _verify_fix(fix)
            fix["verified"] = verified
        else:
            fix["verified"] = None
        verified_fixes.append(fix)

    return {
        "auto_fix_result": {
            "fixes": verified_fixes,
            "total_findings": len(all_findings),
            "fixable_count": len([f for f in verified_fixes if f.get("can_auto_apply")]),
            "summary": f"生成 {len(verified_fixes)} 项修复方案",
        },
    }


async def _verify_fix(fix: dict) -> dict | None:
    """在 Docker 沙箱中验证修复是否有效。"""
    try:
        from mix_agent.tools.sandbox.container import ContainerSandbox

        sandbox = ContainerSandbox()
        if not sandbox.check_available():
            return {"status": "skipped", "reason": "Docker not available"}

        code = fix.get("fixed_snippet", "")
        result = await sandbox.run_code(code, timeout=30)

        if result.exit_code == 0:
            return {"status": "passed", "exit_code": 0}
        else:
            return {"status": "failed", "exit_code": result.exit_code, "stderr": result.stderr[:200]}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
