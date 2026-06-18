"""AutoFix Agent — 可行性分析 + LLM 生成修复 + 文件编辑器实际写入。

工作流：
1. 可行性分析：基于模糊需求 + 现有代码符号表，评估是否可落地
2. 修复生成：LLM 为审计发现生成具体修复 patch
3. 文件编辑：实际将修复写入源文件（含备份）
4. 沙箱验证：Docker 中验证修复后的代码
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from mix_agent.agents.prompts import PromptManager
from mix_agent.services.prompt_store import prompt_store
from mix_agent.schemas import AgentState
from mix_agent.services.llm import llm_client
from mix_agent.services.node_config import get_provider
from mix_agent.tools.parser.ast_analyzer import ASTAnalyzer

_prompts = PromptManager(store=prompt_store)


# ══════════════════════════════════════════════════════════════════
# 文件编辑器
# ══════════════════════════════════════════════════════════════════

class FileEditor:
    """安全的文件编辑器 — 读取、替换、写入，自动备份。"""

    def __init__(self, backup_dir: str | None = None):
        self._backup_dir = Path(backup_dir or tempfile.mkdtemp(prefix="auto_fix_backup_"))
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._modified: list[str] = []

    # ── 公开 API ──

    def read(self, file_path: str) -> str:
        """读取文件全部内容。"""
        return Path(file_path).read_text(encoding="utf-8")

    def apply_diff(self, file_path: str, original_snippet: str, fixed_snippet: str) -> bool:
        """在文件中定位 original_snippet 并替换为 fixed_snippet。

        返回 True 表示成功写入；False 表示未找到匹配片段（不会修改文件）。
        """
        content = self.read(file_path)

        if original_snippet not in content:
            return False

        self._backup(file_path, content)
        new_content = content.replace(original_snippet, fixed_snippet, 1)
        Path(file_path).write_text(new_content, encoding="utf-8")
        self._modified.append(file_path)
        return True

    def apply_patch(self, file_path: str, diff_text: str) -> bool:
        """尝试应用 unified diff patch。

        若原始片段和修复片段可从 diff 中提取，则使用 apply_diff；
        否则回退到简单行替换策略。
        """
        original, fixed = self._parse_diff_snippets(diff_text)
        if original and fixed:
            return self.apply_diff(file_path, original, fixed)

        # 回退：逐行解析 diff hunks
        return self._apply_hunks(file_path, diff_text)

    def rollback(self, file_path: str) -> bool:
        """回滚单个文件到最近一次备份。"""
        backups = sorted(self._backup_dir.glob(f"{Path(file_path).name}.*.bak"))
        if not backups:
            return False
        latest = backups[-1]
        shutil.copy2(str(latest), file_path)
        return True

    def rollback_all(self) -> int:
        """回滚所有修改过的文件，返回回滚数量。"""
        count = 0
        for fp in list(self._modified):
            if self.rollback(fp):
                count += 1
        self._modified.clear()
        return count

    @property
    def modified_files(self) -> list[str]:
        return list(self._modified)

    # ── 内部 ──

    def _backup(self, file_path: str, content: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stem = Path(file_path).name
        backup_path = self._backup_dir / f"{stem}.{ts}.bak"
        backup_path.write_text(content, encoding="utf-8")

    @staticmethod
    def _parse_diff_snippets(diff_text: str) -> tuple[str | None, str | None]:
        """从 unified diff 中提取原始代码和修复代码片段。"""
        lines = diff_text.split("\n")
        original_lines: list[str] = []
        fixed_lines: list[str] = []

        in_original = False
        in_fixed = False
        for line in lines:
            if line.startswith("--- "):
                in_original = True
                in_fixed = False
                continue
            if line.startswith("+++ "):
                in_original = False
                in_fixed = True
                continue
            if line.startswith("@@"):
                in_original = False
                in_fixed = False
                continue
            if line.startswith("-") and not line.startswith("---"):
                original_lines.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                fixed_lines.append(line[1:])
            elif line.startswith(" "):
                original_lines.append(line[1:])
                fixed_lines.append(line[1:])

        orig = "\n".join(original_lines).strip() if original_lines else None
        fixd = "\n".join(fixed_lines).strip() if fixed_lines else None
        return orig, fixd

    def _apply_hunks(self, file_path: str, diff_text: str) -> bool:
        """逐 hunk 应用 diff（简化版）。"""
        content = self.read(file_path)
        content_lines = content.split("\n")
        hunks = self._parse_hunks(diff_text)

        if not hunks:
            return False

        self._backup(file_path, content)
        for hunk in hunks:
            content_lines = self._apply_one_hunk(content_lines, hunk)

        Path(file_path).write_text("\n".join(content_lines), encoding="utf-8")
        self._modified.append(file_path)
        return True

    @staticmethod
    def _parse_hunks(diff_text: str) -> list[dict]:
        """解析 unified diff 中的 hunks。"""
        hunks: list[dict] = []
        current: dict | None = None
        for line in diff_text.split("\n"):
            if line.startswith("@@"):
                if current:
                    hunks.append(current)
                current = {"header": line, "old_start": 0, "new_start": 0, "lines": []}
                # 解析 @@ -a,b +c,d @@
                parts = line.split()
                if len(parts) >= 2:
                    old = parts[1].lstrip("-")
                    if "," in old:
                        current["old_start"] = int(old.split(",")[0])
                if len(parts) >= 3:
                    new = parts[2].lstrip("+")
                    if "," in new:
                        current["new_start"] = int(new.split(",")[0])
            elif current is not None:
                current["lines"].append(line)
        if current:
            hunks.append(current)
        return hunks

    @staticmethod
    def _apply_one_hunk(content_lines: list[str], hunk: dict) -> list[str]:
        """应用单个 hunk 到行列表。"""
        old_start = max(hunk.get("old_start", 1) - 1, 0)  # 0-based
        result: list[str] = []
        hunk_idx = 0
        content_idx = 0

        while content_idx < len(content_lines):
            if content_idx == old_start:
                # 消费 hunk 行
                for hl in hunk["lines"]:
                    if hl.startswith("-") or hl.startswith(" "):
                        # 跳过内容中的对应行
                        if content_idx < len(content_lines):
                            content_idx += 1
                    if hl.startswith("+") or hl.startswith(" "):
                        result.append(hl[1:])
                # 跳过内容中已被 hunk 消费的行
                while content_idx < len(content_lines) and hunk_idx < len(hunk["lines"]):
                    hl = hunk["lines"][hunk_idx]
                    if hl.startswith("-"):
                        content_idx += 1
                        hunk_idx += 1
                    elif hl.startswith(" "):
                        content_idx += 1
                        hunk_idx += 1
                    else:
                        break
                break
            else:
                result.append(content_lines[content_idx])
                content_idx += 1

        # 追加剩余内容
        result.extend(content_lines[content_idx:])
        return result


# ══════════════════════════════════════════════════════════════════
# 可行性分析
# ══════════════════════════════════════════════════════════════════

async def _analyze_feasibility(
    task_description: str,
    changed_files: list[dict],
    ast_symbols: dict,
) -> dict:
    """基于模糊需求和现有代码符号表，分析变更的可行性。

    Args:
        task_description: 用户原始自然语言需求
        changed_files: 变更文件列表
        ast_symbols: AST 符号表（来自 code_review 等节点）

    Returns:
        {
            "feasible": bool,
            "confidence": "high|medium|low",
            "assessment": str,
            "affected_files": [...],
            "risk_level": "low|medium|high",
            "constraints": [...]
        }
    """
    # 构建代码摘要
    code_summary_parts: list[str] = [f"# 用户需求\n{task_description}\n"]

    code_summary_parts.append("# 变更文件")
    for cf in changed_files[:20]:
        code_summary_parts.append(
            f"- {cf.get('file_path', '?')} ({cf.get('change_type', 'modified')})"
        )

    if ast_symbols:
        code_summary_parts.append("\n# 现有代码符号表")
        for file_key, symbols in ast_symbols.items():
            classes = [c.get("name", "") for c in symbols.get("classes", [])]
            funcs = [f.get("name", "") for f in symbols.get("functions", [])]
            if classes or funcs:
                code_summary_parts.append(f"{file_key}: classes={classes}, functions={funcs}")

    code_summary = "\n".join(code_summary_parts)

    # LLM 可行性判断
    try:
        resp = await llm_client.chat_with_prompt(
            provider=get_provider("auto_fix"),
            system_prompt="""你是一名资深软件架构师。基于用户需求和现有代码结构，分析需求的可实现性。

输出 JSON：
{
  "feasible": true/false,
  "confidence": "high|medium|low",
  "assessment": "详细的可行性评估（中文，100字以内）",
  "affected_files": ["需要修改的文件路径"],
  "risk_level": "low|medium|high",
  "constraints": ["技术约束或前置条件"]
}

评估维度：
- 现有代码结构是否支持所需变更
- 改动范围是否可控（文件数、函数数）
- 是否存在明显的技术障碍""",
            user_message=code_summary[:4000],
            temperature=0.2,
            max_tokens=1024,
        )
        content = resp.content.strip().lstrip("```json").rstrip("```")
        feasibility = json.loads(content)
    except Exception:
        feasibility = {
            "feasible": True,
            "confidence": "low",
            "assessment": "LLM 不可用，默认标记为可行（需人工判断）",
            "affected_files": [cf.get("file_path", "") for cf in changed_files[:5]],
            "risk_level": "medium",
            "constraints": ["LLM 不可用，未做深入分析"],
        }

    return feasibility


# ══════════════════════════════════════════════════════════════════
# 沙箱验证
# ══════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════
# 主节点
# ══════════════════════════════════════════════════════════════════

async def auto_fix_node(state: AgentState) -> dict:
    """AutoFix 节点 — 可行性分析 → 修复生成 → 文件编辑 → 沙箱验证。

    1. 分析模糊需求在现有代码基础上的可行性
    2. 收集所有 agent 的 danger/warning 发现项
    3. LLM 生成修复 patch
    4. 使用 FileEditor 将修复实际写入文件
    5. Docker 沙箱验证修复
    """
    all_findings: list[dict] = []
    editor = FileEditor()

    # ── Step 1: 可行性分析 ──
    task_desc = state.task_description or "未指定需求"
    feasibility = await _analyze_feasibility(
        task_description=task_desc,
        changed_files=state.changed_files,
        ast_symbols=state.ast_symbols,
    )

    # ── Step 2: 收集发现项 ──
    for result_key in [
        "code_review_result", "sql_audit_result",
        "api_path_result", "compliance_result",
    ]:
        result = getattr(state, result_key, {}) or {}
        items = result.get("findings", []) or result.get("violations", [])
        for item in items:
            if isinstance(item, dict) and item.get("severity") in ("danger", "warning"):
                all_findings.append(item)

    if not all_findings:
        return {
            "auto_fix_result": {
                "feasibility": feasibility,
                "fixes": [],
                "summary": "无需要修复的高危发现",
                "files_modified": [],
            },
        }

    # ── Step 3: LLM 生成修复 ──
    prompt = _prompts.get("auto_fix")
    fixes: list[dict] = []
    try:
        # 把可行性分析结果也传给 LLM 以供参考
        user_input = json.dumps({
            "feasibility_analysis": feasibility,
            "findings": all_findings[:10],
        }, ensure_ascii=False, default=str)

        resp = await llm_client.chat_with_prompt(
            provider=get_provider("auto_fix"),
            system_prompt=prompt.system,
            user_message=user_input,
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

    # ── Step 4: 文件编辑 — 实际写入修复 ──
    applied_count = 0
    for fix in fixes:
        file_path = fix.get("file", "")
        can_apply = fix.get("can_auto_apply", False)

        if not can_apply or not file_path or not os.path.isfile(file_path):
            fix["applied"] = False
            fix["apply_error"] = "文件不存在或不可自动应用" if not can_apply else None
            continue

        original = fix.get("original_snippet", "")
        fixed = fix.get("fixed_snippet", "")

        if original and fixed:
            ok = editor.apply_diff(file_path, original, fixed)
            fix["applied"] = ok
            if not ok:
                fix["apply_error"] = "未在文件中找到匹配的原始片段"
            else:
                applied_count += 1
        else:
            # 尝试 diff
            diff_text = fix.get("diff", "")
            if diff_text:
                ok = editor.apply_patch(file_path, diff_text)
                fix["applied"] = ok
                if not ok:
                    fix["apply_error"] = "diff 应用失败"
                else:
                    applied_count += 1
            else:
                fix["applied"] = False
                fix["apply_error"] = "缺少 original_snippet/fixed_snippet 或 diff"

    # ── Step 5: 沙箱验证 ──
    for fix in fixes:
        if fix.get("applied") and fix.get("fixed_snippet"):
            verified = await _verify_fix(fix)
            fix["verified"] = verified
        else:
            fix["verified"] = None

    # 若可行性低或风险高，回滚所有修改
    if feasibility.get("risk_level") == "high" and not feasibility.get("feasible"):
        rolled = editor.rollback_all()
        summary = (
            f"可行性低且风险高，已回滚 {rolled} 个文件。"
            f"共生成 {len(fixes)} 项修复方案，均需人工审查。"
        )
    else:
        summary = (
            f"可行性: {feasibility.get('assessment', 'N/A')}。"
            f"共生成 {len(fixes)} 项修复方案，"
            f"实际应用 {applied_count} 项到文件。"
        )

    return {
        "auto_fix_result": {
            "feasibility": feasibility,
            "fixes": fixes,
            "total_findings": len(all_findings),
            "fixable_count": len([f for f in fixes if f.get("can_auto_apply")]),
            "applied_count": applied_count,
            "files_modified": editor.modified_files,
            "summary": summary,
        },
    }
