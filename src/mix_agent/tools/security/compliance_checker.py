"""合规扫描器 — 基于 YAML 规则引擎检测 OWASP/GDPR/PCI-DSS/等保 违规。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ComplianceViolation:
    """单条合规违规。"""
    rule_id: str
    category: str
    severity: str
    description: str
    file_path: str = ""
    line_number: int = 0
    evidence: str = ""


@dataclass
class ComplianceResult:
    """合规扫描结果。"""
    violations: list[ComplianceViolation] = field(default_factory=list)
    files_scanned: int = 0
    rules_checked: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)


class ComplianceChecker:
    """YAML 规则驱动的合规扫描器。

    支持 OWASP Top 10、GDPR、PCI-DSS、等保 2.0 等多标准。
    规则文件位于 compliance_rules/ 目录。
    """

    def __init__(self, rules_dir: str | Path | None = None):
        if rules_dir is None:
            rules_dir = Path(__file__).parent.parent.parent / "compliance_rules"
        self.rules_dir = Path(rules_dir)
        self._rules: list[dict] = []
        self._load_rules()

    # ── 公开 API ──

    def scan_files(self, file_paths: list[str | Path]) -> ComplianceResult:
        """扫描指定文件列表。"""
        result = ComplianceResult(rules_checked=len(self._rules))

        for fp in file_paths:
            path = Path(fp)
            if not path.exists() or path.suffix not in (".py", ".toml", ".yaml", ".yml", ".json", ".js", ".ts", ".tsx"):
                continue

            result.files_scanned += 1
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for rule in self._rules:
                violations = self._check_rule(rule, content, str(path))
                result.violations.extend(violations)

        # 汇总统计
        for v in result.violations:
            result.by_category[v.category] = result.by_category.get(v.category, 0) + 1
            result.by_severity[v.severity] = result.by_severity.get(v.severity, 0) + 1

        return result

    def scan_directory(self, root: str | Path = ".") -> ComplianceResult:
        """扫描整个目录。"""
        root_path = Path(root)
        file_paths = [
            str(p) for p in root_path.rglob("*")
            if p.is_file() and "__pycache__" not in str(p)
            and ".git" not in str(p) and "node_modules" not in str(p)
        ]
        return self.scan_files(file_paths)

    # ── 内部实现 ──

    def _load_rules(self) -> None:
        """加载所有 YAML 规则文件。"""
        if not self.rules_dir.exists():
            return

        for yaml_file in self.rules_dir.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "rules" in data:
                        self._rules.extend(data["rules"])
            except Exception:
                pass

    def _check_rule(self, rule: dict, content: str, file_path: str) -> list[ComplianceViolation]:
        """对单个文件执行单条规则检查。"""
        violations: list[ComplianceViolation] = []
        rule_id = rule.get("id", "unknown")
        category = rule.get("category", "")
        severity = rule.get("severity", "warning")
        description = rule.get("description", "")

        for pattern_def in rule.get("patterns", []):
            ptype = pattern_def.get("type", "")

            if ptype == "file_content":
                keywords = pattern_def.get("keywords", [])
                for keyword in keywords:
                    if keyword.lower() in content.lower():
                        violations.append(ComplianceViolation(
                            rule_id=rule_id,
                            category=category,
                            severity=severity,
                            description=f"{description} (matched: {keyword})",
                            file_path=file_path,
                            evidence=f"Contains '{keyword}'",
                        ))
                        break  # 每条规则每个文件只报一次

            elif ptype == "regex":
                pattern = pattern_def.get("pattern", "")
                if pattern:
                    try:
                        if re.search(pattern, content):
                            violations.append(ComplianceViolation(
                                rule_id=rule_id,
                                category=category,
                                severity=severity,
                                description=description,
                                file_path=file_path,
                                evidence=f"Matches regex: {pattern[:100]}",
                            ))
                    except re.error:
                        pass

            elif ptype == "file_check":
                files = pattern_def.get("files", [])
                for f in files:
                    if f in file_path:
                        violations.append(ComplianceViolation(
                            rule_id=rule_id,
                            category=category,
                            severity=severity,
                            description=f"{description} (found: {f})",
                            file_path=file_path,
                        ))

            elif ptype == "missing_pattern":
                pattern = pattern_def.get("pattern", "")
                if pattern and pattern not in content:
                    # 只对特定文件类型检查缺失
                    if file_path.endswith((".py", ".env", ".toml", ".cfg")):
                        violations.append(ComplianceViolation(
                            rule_id=rule_id,
                            category=category,
                            severity=severity,
                            description=f"{description} (missing: {pattern})",
                            file_path=file_path,
                        ))

        return violations
