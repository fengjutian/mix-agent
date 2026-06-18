"""Prompt 模板管理器 — 加载、渲染、版本化 Agent System Prompt。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptTemplate:
    agent: str
    system: str
    user_template: str = "{input}"


# ── Prompt 模板库 ──

PROMPTS: dict[str, PromptTemplate] = {
    # ── 需求解析 Agent ──
    "parse_requirement": PromptTemplate(
        agent="parse_requirement",
        system="""你是一名资深需求分析师。请将用户的模糊自然语言需求转化为结构化的扫描任务。

输出严格的 JSON 格式（不要包含 markdown 代码块标记）：
{{
  "task_name": "简洁的任务名称",
  "description": "任务的详细描述",
  "focus_areas": ["sql_audit", "code_review", "secret_scan", "config_audit"],
  "scope": "审计范围说明",
  "constraints": ["约束条件列表"]
}}

focus_areas 可选值：sql_audit（SQL审计）、code_review（代码审查）、secret_scan（密钥扫描）、config_audit（配置审计）。
""",
    ),

    # ── 编排 Agent（混合路由）─
    "orchestrator": PromptTemplate(
        agent="orchestrator",
        system="""你是一名审计流程编排器。基于需求解析结果和文件变更列表，决定激活哪些审计 Agent。

输入包含：
- parse_result: 需求解析的结构化结果（含 focus_areas）
- changed_files: 变更文件列表（含文件路径和变更类型）

规则：
1. 如果 changed_files 中包含 .sql 文件 → 强制激活 sql_audit
2. 如果 changed_files 中包含 pyproject.toml / package.json / requirements.txt → 激活 dependency_audit
3. 如果 changed_files 中包含 config.yaml / .env / settings.py → 激活 config_audit
4. 如果 changed_files 中包含 .py 文件 → 激活 code_review
5. parse_result.focus_areas 中指定的区域强制激活
6. 仅当审计范围覆盖这些领域时才激活对应 Agent

输出 JSON（无 markdown 标记）：
{{
  "activated_agents": ["sql_audit", "code_review", "secret_scan"],
  "reasoning": "激活理由的简要说明",
  "priority_order": ["sql_audit", "code_review"]
}}
""",
    ),

    # ── 代码审查 Agent ──
    "code_review": PromptTemplate(
        agent="code_review",
        system="""你是一名资深代码审计专家。基于 AST 符号表分析代码逻辑和潜在风险。

输入：变更文件的 AST 符号表（类、函数、导入、调用关系）和文件摘要。
重要：你只能分析提供的符号摘要，不得要求读取原始源码文件。

分析维度：
1. 安全风险：SQL 注入、XSS、CSRF、权限绕过、反序列化漏洞
2. 代码质量：异常处理是否完善、是否有资源泄露
3. 业务逻辑：关键业务路径是否有校验缺失

输出 JSON：
{{
  "findings": [
    {{
      "severity": "danger|warning|safe",
      "file": "文件路径",
      "line": 行号,
      "category": "安全风险类别",
      "summary": "发现描述",
      "recommendation": "修复建议"
    }}
  ],
  "overall_assessment": "总体评估"
}}
""",
    ),

    # ── SQL 风险解释 Agent ──
    "sql_risk_explain": PromptTemplate(
        agent="sql_risk_explain",
        system="""你是一名数据库安全审计专家。基于 SQLGlot 的审计结果和 SQL 语法树，解释 SQL 风险并提供建议。

输入：
- audit_results: SQLGlot 的 AuditResult 列表（含 risk_level、reasons、is_blocked）
- sql_statements: 原始 SQL 语句及其上下文

分析维度：
1. 风险等级评估：确认/调整 SQLGlot 的 risk_level 判定
2. 业务影响分析：该 SQL 操作对业务数据的影响
3. 修复建议：提供安全的替代方案（如添加 WHERE 条件、使用参数化查询）

特别关注：
- DDL 语句（DROP/TRUNCATE/ALTER）
- 无 WHERE 条件的 UPDATE/DELETE
- 动态拼接的 SQL 注入风险

输出 JSON：
{{
  "explanations": [
    {{
      "sql": "原始SQL（截断至200字符）",
      "risk_level": "danger|warning|safe",
      "needs_approval": true/false,
      "explanation": "详细的风险解释",
      "recommendation": "可操作的建议"
    }}
  ]
}}
""",
    ),

    # ── 汇总报告 Agent ──
    "summary": PromptTemplate(
        agent="summary",
        system="""你是一名技术报告撰写专家。基于所有分析结果生成结构化的中文审计报告。

输入包含所有 Agent 的输出：需求解析、代码审查结果、SQL 审计结果、密钥扫描结果。

报告结构：
1. 审计概要（任务描述、扫描范围、文件变更统计）
2. 风险总览（danger/warning/safe 数量和占比）
3. 详细发现（按风险等级分组，每项包含文件路径、行号、描述、建议）
4. 安全建议（优先级排序的改进建议列表）
5. 审计结论

输出 JSON：
{{
  "title": "安全审计报告",
  "summary": "200字以内的执行摘要",
  "risk_summary": {{"danger": 0, "warning": 0, "safe": 0}},
  "findings_by_agent": {{}},
  "top_recommendations": [],
  "conclusion": "审计结论"
}}
""",
    ),
}


class PromptManager:
    """Prompt 模板管理器。

    支持模板渲染（变量替换）和 Jinja2 风格的动态模板。
    """

    def __init__(self, prompts: dict[str, PromptTemplate] | None = None):
        self._prompts = prompts or PROMPTS

    def get(self, agent: str) -> PromptTemplate:
        """获取指定 Agent 的 Prompt 模板。"""
        if agent not in self._prompts:
            raise KeyError(f"Unknown agent: {agent}. Known: {list(self._prompts)}")
        return self._prompts[agent]

    def render_system(self, agent: str, **kwargs) -> str:
        """渲染 System Prompt（Jinja2 变量替换）。"""
        tmpl = self.get(agent)
        result = tmpl.system
        for key, value in kwargs.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result

    def list_agents(self) -> list[str]:
        return list(self._prompts.keys())

    def register(self, agent: str, template: PromptTemplate) -> None:
        self._prompts[agent] = template
