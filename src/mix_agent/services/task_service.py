"""任务服务 — 编排工具层执行审计流水线（Phase 1 确定性扫描）。"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from mix_agent.schemas import (
    FindingItem,
    FindingsResponse,
    ReportResponse,
    TaskDetail,
    TaskStatus,
)
from mix_agent.tools.parser.ast_analyzer import ASTAnalyzer
from mix_agent.tools.security.secret_scanner import SecretScanner
from mix_agent.tools.security.sql_guard import RiskLevel, SQLGuard
from mix_agent.tools.vcs.git_tool import GitTool


class TaskService:
    """Phase 1 任务编排服务。

    接收扫描请求 → Git Diff → AST 分析 → SQL 审计 → 密钥扫描 → 汇总报告。
    所有操作均为确定性，不调用 LLM。
    """

    def __init__(self):
        # 内存任务存储（Phase 1 原型；生产环境替换为 PostgreSQL）
        self._tasks: dict[str, dict[str, Any]] = {}
        self._findings: dict[str, list[FindingItem]] = {}
        self._reports: dict[str, dict[str, Any]] = {}

    # ── 任务生命周期 ──

    def create_task(
        self,
        description: str = "",
        target_branch: str = "HEAD",
        base_branch: str = "main",
        repo_path: str = ".",
    ) -> TaskDetail:
        """创建并执行审计任务。"""
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        task = {
            "task_id": task_id,
            "status": TaskStatus.RUNNING,
            "description": description,
            "target_branch": target_branch,
            "base_branch": base_branch,
            "repo_path": repo_path,
            "created_at": now,
            "completed_at": None,
        }
        self._tasks[task_id] = task

        try:
            findings, report = self._run_analysis(repo_path, target_branch, base_branch)
            task["status"] = TaskStatus.COMPLETED
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._findings[task_id] = findings
            self._reports[task_id] = report
        except Exception as e:
            task["status"] = TaskStatus.FAILED
            task["error"] = str(e)

        return TaskDetail(**task)

    def get_task(self, task_id: str) -> TaskDetail | None:
        """查询任务状态。"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return TaskDetail(**task)

    def get_findings(self, task_id: str) -> FindingsResponse | None:
        """查询任务发现项。"""
        if task_id not in self._tasks:
            return None
        findings = self._findings.get(task_id, [])
        return FindingsResponse(
            task_id=task_id,
            findings=findings,
            total=len(findings),
        )

    def get_report(self, task_id: str, fmt: str = "json") -> ReportResponse | None:
        """获取审计报告。"""
        if task_id not in self._tasks:
            return None
        report = self._reports.get(task_id, {})
        findings = self._findings.get(task_id, [])

        danger = sum(1 for f in findings if f.risk_level == "danger")
        warning = sum(1 for f in findings if f.risk_level == "warning")

        return ReportResponse(
            task_id=task_id,
            format=fmt,
            summary=report.get("summary", ""),
            total_findings=len(findings),
            danger_count=danger,
            warning_count=warning,
            changed_files=report.get("changed_files", []),
            findings=findings,
            ast_symbols=report.get("ast_symbols", {}),
        )

    def cancel_task(self, task_id: str) -> TaskDetail | None:
        """取消任务。"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task["status"] in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task["status"] = TaskStatus.CANCELLED
        return TaskDetail(**task)

    # ── 内部分析流水线 ──

    def _run_analysis(
        self, repo_path: str, target: str, base: str
    ) -> tuple[list[FindingItem], dict[str, Any]]:
        """执行完整的分析流水线。"""
        findings: list[FindingItem] = []

        # 1. Git Diff
        git = GitTool(repo_path)
        diff_result = git.diff(target=target, base=base)

        for f in diff_result.changed_files:
            findings.append(FindingItem(
                agent="git_diff",
                finding_type="file_change",
                risk_level="safe",
                file_path=f.file_path,
                description=f"File {f.change_type.value}: +{f.additions}/-{f.deletions}",
            ))

        # 2. Secret Scanner
        changed_paths = [
            os.path.join(repo_path, f.file_path)
            for f in diff_result.changed_files
            if f.change_type.value != "deleted"
        ]
        if changed_paths:
            scanner = SecretScanner()
            scan_result = scanner.scan(changed_paths)
            for sf in scan_result.findings:
                findings.append(FindingItem(
                    agent="secret_scanner",
                    finding_type=sf.rule_id,
                    risk_level=sf.severity,
                    file_path=os.path.relpath(sf.file_path, repo_path),
                    line_number=sf.line_number,
                    code_snippet=sf.line_content.strip(),
                    description=sf.description,
                    recommendation="将敏感信息移至环境变量或密钥管理服务",
                ))

        # 3. SQL Audit
        for f in diff_result.changed_files:
            if not f.file_path.endswith(".sql") and not f.file_path.endswith(".py"):
                continue
            # 对 .py 文件提取 SQL 字符串进行审计（简化：仅审计 .sql 文件）
            if f.file_path.endswith(".sql"):
                try:
                    full_path = os.path.join(repo_path, f.file_path)
                    with open(full_path, encoding="utf-8") as fh:
                        sql_content = fh.read()
                    guard = SQLGuard()
                    sql_statements = [s.strip() for s in sql_content.split(";") if s.strip()]
                    for stmt in sql_statements:
                        result = guard.audit(stmt)
                        if result.risk_level != RiskLevel.SAFE:
                            findings.append(FindingItem(
                                agent="sql_guard",
                                finding_type="sql_risk",
                                risk_level=result.risk_level.value,
                                file_path=f.file_path,
                                code_snippet=stmt[:200],
                                description="; ".join(result.reasons),
                                recommendation="请审查该 SQL 语句的安全性" if result.is_blocked else "",
                            ))
                except OSError:
                    pass

        # 4. AST Analysis
        py_files = [p for p in changed_paths if p.endswith(".py")]
        if py_files:
            ana = ASTAnalyzer()
            ast_result = ana.parse_files(py_files)
            # Summarize
            for file_key, symbols in ast_result.get("files", {}).items():
                rel_path = os.path.relpath(file_key, repo_path)
                findings.append(FindingItem(
                    agent="ast_analyzer",
                    finding_type="code_structure",
                    risk_level="safe",
                    file_path=rel_path,
                    description=ana.generate_summary(
                        open(file_key, encoding="utf-8").read()
                    ) if os.path.exists(file_key) else "",
                ))

        # Build report
        report = {
            "summary": f"Audit completed: {len(diff_result.changed_files)} files changed, "
                       f"{len(findings)} findings total",
            "changed_files": [f.to_dict() for f in diff_result.changed_files],
            "ast_symbols": ast_result if py_files else {},
            "diff_stats": {
                "total_additions": diff_result.total_additions,
                "total_deletions": diff_result.total_deletions,
            },
        }

        return findings, report


# 单例
task_service = TaskService()


