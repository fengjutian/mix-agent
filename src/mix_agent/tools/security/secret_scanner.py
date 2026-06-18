"""密钥与配置安全扫描器 — 检测源码中硬编码的 API Key、密码、Token 等敏感信息。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SecretFinding:
    """单条密钥发现项。"""
    file_path: str
    line_number: int
    line_content: str
    rule_id: str
    severity: str  # "danger" | "warning"
    description: str


@dataclass
class ScanResult:
    """扫描结果汇总。"""
    findings: list[SecretFinding] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0

    @property
    def danger_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "danger")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


# ── 规则定义 ──
# 每条规则包含: (rule_id, severity, regex_pattern, description)
SECRET_RULES: list[tuple[str, str, str, str]] = [
    # 通用 API Key 模板
    (
        "api_key_assignment",
        "danger",
        r'(?i)(api[_-]?key|apikey|api[_-]?secret|access[_-]?key|secret[_-]?key)\s*[:=]\s*["\'][A-Za-z0-9_\-+/=]{8,}["\']',
        "明文 API Key 赋值",
    ),
    # OpenAI / Anthropic API Key 格式
    (
        "openai_key",
        "danger",
        r'sk-(?:proj-)?[A-Za-z0-9_\-]{20,}',
        "OpenAI / 类 OpenAI API Key 格式",
    ),
    # Anthropic API Key
    (
        "anthropic_key",
        "danger",
        r'sk-ant-[A-Za-z0-9_\-]{20,}',
        "Anthropic API Key",
    ),
    # AWS Access Key
    (
        "aws_access_key",
        "danger",
        r'(?:AKIA|ASIA)[A-Z0-9]{16}',
        "AWS Access Key ID",
    ),
    # AWS Secret Key
    (
        "aws_secret_key",
        "danger",
        r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\'][A-Za-z0-9/+]{20,}["\']',
        "AWS Secret Access Key",
    ),
    # 通用密码赋值
    (
        "password_assignment",
        "warning",
        r'(?i)(?:password|passwd|pwd|secret)\s*[:=]\s*["\'][^"\'\s]{4,}["\']',
        "疑似明文密码赋值",
    ),
    # JWT Token
    (
        "jwt_token",
        "warning",
        r'eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}',
        "硬编码 JWT Token",
    ),
    # 私钥头
    (
        "private_key_header",
        "danger",
        r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
        "硬编码私钥",
    ),
    # 数据库连接串（含密码）
    (
        "db_connection_string",
        "warning",
        r'(?i)(?:mysql|postgres(?:ql)?|mongodb|redis)://[^/\s]+:[^@\s]+@',
        "数据库连接串含明文密码",
    ),
    # GitHub Token
    (
        "github_token",
        "danger",
        r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}',
        "GitHub Personal Access Token",
    ),
    # 通用 Token / Bearer
    (
        "generic_token",
        "warning",
        r'(?i)(?:token|auth[_-]?token|bearer)\s*[:=]\s*["\'][A-Za-z0-9_\-\.]{10,}["\']',
        "疑似硬编码 Token",
    ),
]


class SecretScanner:
    """密钥与配置安全扫描器。

    使用正则表达式模式库检测源码和配置文件中是否包含硬编码的敏感信息，
    如 API Key、密码、Token、私钥等。
    """

    # 跳过这些目录和文件类型
    SKIP_DIRS: set[str] = {".git", ".svn", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
    SKIP_EXTENSIONS: set[str] = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".jpg", ".png", ".gif", ".ico", ".pdf"}
    # 仅扫描这些扩展名（空集合 = 全部扫描）
    SCAN_EXTENSIONS: set[str] = set()

    def __init__(self, rules: list[tuple[str, str, str, str]] | None = None):
        self.rules = rules or SECRET_RULES
        self._patterns: list[tuple[str, str, re.Pattern, str]] = [
            (rule_id, severity, re.compile(pattern), description)
            for rule_id, severity, pattern, description in self.rules
        ]

    # ── 公开接口 ──

    def scan(self, file_paths: list[str | Path]) -> ScanResult:
        """扫描指定文件列表，返回所有敏感信息发现项。"""
        result = ScanResult()

        for fp in file_paths:
            path = Path(fp)
            if self._should_skip(path):
                result.files_skipped += 1
                continue

            result.files_scanned += 1
            findings = self._scan_file(path)
            result.findings.extend(findings)

        return result

    def scan_dir(self, root: str | Path = ".", recursive: bool = True) -> ScanResult:
        """扫描目录下所有文件。"""
        root_path = Path(root).resolve()
        file_paths: list[str] = []

        for path in root_path.rglob("*") if recursive else root_path.glob("*"):
            if path.is_file():
                file_paths.append(str(path))

        return self.scan(file_paths)

    def scan_content(self, content: str, file_name: str = "<string>") -> list[SecretFinding]:
        """扫描给定文本内容（不读取文件）。"""
        findings: list[SecretFinding] = []
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            for rule_id, severity, pattern, description in self._patterns:
                if pattern.search(line):
                    # 跳过注释行（以 # 或 // 或 -- 开头）
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("--"):
                        continue
                    # 跳过 import / from 语句
                    if stripped.startswith("import ") or stripped.startswith("from "):
                        continue

                    findings.append(SecretFinding(
                        file_path=file_name,
                        line_number=i,
                        line_content=line,
                        rule_id=rule_id,
                        severity=severity,
                        description=description,
                    ))
                    break  # 每行只报一次

        return findings

    # ── 内部实现 ──

    def _scan_file(self, path: Path) -> list[SecretFinding]:
        """扫描单个文件。"""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return self.scan_content(content, str(path))
        except OSError:
            return []

    def _should_skip(self, path: Path) -> bool:
        """判断是否应跳过该文件。"""
        # 检查路径中的目录名
        parts = path.parts
        for skip_dir in self.SKIP_DIRS:
            if skip_dir in parts:
                return True

        # 检查扩展名
        ext = path.suffix.lower()
        if ext in self.SKIP_EXTENSIONS:
            return True

        # 如果有白名单扩展名，只扫描白名单
        if self.SCAN_EXTENSIONS and ext not in self.SCAN_EXTENSIONS:
            return True

        return False
