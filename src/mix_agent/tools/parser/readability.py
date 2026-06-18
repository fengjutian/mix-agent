"""F22 AI 代码可读化 — 4 层滤网，Layer 1+2 优先。

Layer 1: 意图摘要 — 一句话说明代码目的
Layer 2: Diff 锚点 — 精确定位变更点和影响范围
Layer 3: 上下文解释 — 代码在业务中的角色
Layer 4: 风险评估 — 变更的安全影响评估
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ReadabilityLayer:
    """单层可读化结果。"""
    layer: int
    name: str
    content: str
    priority: str = "low"  # "high" | "medium" | "low"


@dataclass
class ReadabilityResult:
    """代码可读化完整结果。"""
    file_path: str
    layers: list[ReadabilityLayer] = field(default_factory=list)
    generated_at: str = ""

    @property
    def intent(self) -> str:
        """Layer 1: 意图摘要。"""
        for l in self.layers:
            if l.layer == 1:
                return l.content
        return ""

    @property
    def anchors(self) -> list[str]:
        """Layer 2: Diff 锚点列表。"""
        for l in self.layers:
            if l.layer == 2:
                return [a.strip() for a in l.content.split("\n") if a.strip()]
        return []

    def to_prompt_context(self, max_layers: int = 2) -> str:
        """将 Layer 1+2 拼接为 Agent Prompt 上下文。"""
        parts: list[str] = []
        for l in self.layers:
            if l.layer <= max_layers:
                parts.append(f"[{l.name}] {l.content}")
        return "\n".join(parts)


class ReadabilityFilter:
    """F22 代码可读化引擎。

    Layer 1 (意图摘要): 纯规则 — 从 AST 符号表生成，无需 LLM
    Layer 2 (Diff 锚点): 纯规则 — Git diff hunks → 变更定位
    Layer 3 (上下文解释): LLM — 需要时按需生成
    Layer 4 (风险评估): LLM — 仅 danger 级别触发
    """

    def __init__(self):
        pass

    # ── Layer 1: 意图摘要（纯规则，零成本） ──

    def layer1_intent(self, file_path: str, source: str) -> ReadabilityLayer:
        """从源码生成意图摘要：模块 docstring + 类/函数列表。"""
        import ast

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ReadabilityLayer(
                layer=1, name="意图摘要",
                content=f"文件 {file_path}（解析失败）",
                priority="high",
            )

        doc = ast.get_docstring(tree)
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef) if not n.name.startswith("_")]
        functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) if not n.name.startswith("_")]

        parts = []
        if doc:
            parts.append(doc.split("\n")[0][:100])
        if classes:
            parts.append(f"类: {', '.join(classes[:5])}")
        if functions:
            parts.append(f"函数: {', '.join(functions[:8])}")

        content = "。".join(parts) if parts else f"模块: {file_path}"
        return ReadabilityLayer(layer=1, name="意图摘要", content=content, priority="high")

    # ── Layer 2: Diff 锚点（纯规则，零成本） ──

    def layer2_anchors(self, file_path: str, diff_hunks: list[str]) -> ReadabilityLayer:
        """从 git diff hunks 提取变更定位锚点。"""
        if not diff_hunks:
            return ReadabilityLayer(layer=2, name="Diff 锚点", content="无变更", priority="high")

        anchors: list[str] = []
        for hunk in diff_hunks:
            lines = hunk.split("\n")
            for line in lines:
                # 提取 @@ -x,y +a,b @@ 行
                if line.startswith("@@"):
                    anchors.append(f"变更锚点: {line.strip()}")
                # 提取新增/修改的函数名
                elif line.startswith("+") and ("def " in line or "class " in line):
                    name = line.lstrip("+").strip()
                    anchors.append(f"新增: {name[:80]}")
                elif line.startswith("-") and ("def " in line or "class " in line):
                    name = line.lstrip("-").strip()
                    anchors.append(f"删除: {name[:80]}")

        if not anchors:
            anchors = ["无函数级变更"]

        return ReadabilityLayer(
            layer=2, name="Diff 锚点",
            content="\n".join(anchors[:10]),
            priority="high",
        )

    # ── Layer 3+4: LLM 增强（按需） ──

    async def layer3_context(self, file_path: str, layer1: str, layer2: str) -> ReadabilityLayer:
        """Layer 3: LLM 解释代码在业务上下文中的角色。"""
        try:
            from mix_agent.services.llm import llm_client

            resp = await llm_client.chat_with_prompt(
                provider="deepseek",
                system_prompt="你是代码分析专家。简要说明代码文件在系统中的角色和职责。最多3句话。",
                user_message=f"文件: {file_path}\n意图: {layer1}\n变更: {layer2}",
                temperature=0.1,
                max_tokens=256,
            )
            content = resp.content.strip()
        except Exception:
            content = f"（LLM 不可用）文件 {file_path} 的业务角色需要人工评估"

        return ReadabilityLayer(layer=3, name="上下文解释", content=content, priority="medium")

    async def layer4_risk(self, findings: list[dict]) -> ReadabilityLayer:
        """Layer 4: LLM 评估变更的安全风险。"""
        if not findings:
            return ReadabilityLayer(layer=4, name="风险评估", content="无安全发现", priority="low")

        try:
            from mix_agent.services.llm import llm_client

            resp = await llm_client.chat_with_prompt(
                provider="deepseek",
                system_prompt="你是安全专家。基于审计发现评估变更的整体风险等级和影响范围。最多5句话。",
                user_message=json.dumps(findings, ensure_ascii=False, default=str)[:2000],
                temperature=0.1,
                max_tokens=512,
            )
            content = resp.content.strip()
        except Exception:
            content = f"发现 {len(findings)} 项安全问题（需人工评估）"

        return ReadabilityLayer(layer=4, name="风险评估", content=content, priority="low")

    # ── 完整分析 ──

    def analyze_file(self, file_path: str, source: str, diff_hunks: list[str] | None = None) -> ReadabilityResult:
        """对单个文件执行 Layer 1+2 分析（零 LLM 成本）。"""
        result = ReadabilityResult(file_path=file_path)
        result.layers.append(self.layer1_intent(file_path, source))

        if diff_hunks:
            result.layers.append(self.layer2_anchors(file_path, diff_hunks))
        else:
            result.layers.append(ReadabilityLayer(layer=2, name="Diff 锚点", content="（无 diff 数据）", priority="high"))

        return result

    async def enhance(self, result: ReadabilityResult, findings: list[dict] | None = None) -> None:
        """按需补充 Layer 3+4（调用 LLM）。"""
        l1 = result.layers[0].content if result.layers else ""
        l2 = result.layers[1].content if len(result.layers) > 1 else ""

        # Layer 3: 始终生成
        l3 = await self.layer3_context(result.file_path, l1, l2)
        result.layers.append(l3)

        # Layer 4: 仅在有发现时生成
        if findings:
            l4 = await self.layer4_risk(findings)
            result.layers.append(l4)
