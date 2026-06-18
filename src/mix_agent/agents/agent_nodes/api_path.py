"""API 路径安全分析 Agent — 检测未鉴权路由、敏感操作暴露等风险。"""

from __future__ import annotations

import json

from mix_agent.agents.prompts import PromptManager
from mix_agent.schemas import AgentState
from mix_agent.services.llm import llm_client
from mix_agent.services.node_config import get_provider
from mix_agent.tools.parser.route_scanner import RouteScanner

_prompts = PromptManager()

# 注册 API Path Agent 专用 prompt
_prompts.register("api_path", type(_prompts.get("code_review"))(
    agent="api_path",
    system="""你是一名 API 安全专家。分析扫描到的路由列表，识别安全隐患。

输入：
- routes: 所有路由列表（method, path, handler, has_auth, auth_deps）
- unauthenticated_routes: 未鉴权路由

重点关注：
1. 未鉴权的敏感操作（如 /admin/*, /api/*/delete, /api/*/cancel）
2. GET 端点是否存在数据泄露风险
3. 路径参数是否可能被遍历

输出 JSON：
{
  "findings": [
    {
      "severity": "danger|warning|safe",
      "route": "METHOD /path",
      "issue": "问题描述",
      "recommendation": "修复建议"
    }
  ],
  "overall_risk": "low|medium|high"
}
"""
))


async def api_path_node(state: AgentState) -> dict:
    """API 路径分析节点。

    1. 调用 RouteScanner 扫描变更文件中的路由定义
    2. 将分析结果发送给 LLM 进行安全审查
    """
    # 收集变更的 Python 文件
    py_files = [
        cf["file_path"]
        for cf in state.changed_files
        if cf.get("file_path", "").endswith(".py")
        and cf.get("change_type") != "deleted"
    ]

    if not py_files:
        return {"api_path_result": {"findings": [], "overall_risk": "low"}}

    # 扫描路由
    scanner = RouteScanner()
    merged = scanner.scan_files(py_files)

    all_routes: list[dict] = []
    unauthenticated: list[dict] = []

    for file_path, result in merged.items():
        for route in result.routes:
            info = {
                "method": route.method,
                "path": route.path,
                "handler": route.handler,
                "file": route.file_path,
                "has_auth": route.has_auth,
                "auth_deps": route.auth_deps,
            }
            all_routes.append(info)
            if not route.has_auth:
                unauthenticated.append(info)

    if not all_routes:
        return {"api_path_result": {"findings": [], "overall_risk": "low"}}

    # 规则引擎：快速检测不安全的未鉴权路由
    rule_findings: list[dict] = []
    SENSITIVE_PATTERNS = ["admin", "delete", "cancel", "config", "secret"]

    for route in unauthenticated:
        path_lower = route["path"].lower()
        for pattern in SENSITIVE_PATTERNS:
            if pattern in path_lower:
                rule_findings.append({
                    "severity": "danger",
                    "route": f'{route["method"]} {route["path"]}',
                    "issue": f"未鉴权的敏感路由 (匹配 '{pattern}')",
                    "recommendation": f"为 {route['handler']} 添加 Depends(get_current_user) 鉴权",
                })
                break

    # LLM 补充分析
    llm_findings: list[dict] = []
    try:
        resp = await llm_client.chat_with_prompt(
            provider=get_provider("api_path"),
            system_prompt=_prompts.get("api_path").system,
            user_message=json.dumps({
                "routes": all_routes[:50],
                "unauthenticated_routes": unauthenticated[:50],
            }, ensure_ascii=False),
            temperature=0.2,
            max_tokens=1024,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        llm_result = json.loads(content)
        llm_findings = llm_result.get("findings", [])
    except Exception:
        pass

    all_findings = rule_findings + llm_findings
    overall_risk = "high" if any(f["severity"] == "danger" for f in all_findings) else \
                   "medium" if all_findings else "low"

    return {
        "api_path_result": {
            "findings": all_findings,
            "total_routes": len(all_routes),
            "unauthenticated_count": len(unauthenticated),
            "overall_risk": overall_risk,
        },
    }
