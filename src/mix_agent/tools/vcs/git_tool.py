"""Git 差异分析工具 — 通过 git CLI 获取两个分支间的文件变更列表。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class ChangedFile:
    """单个变更文件信息。"""
    file_path: str
    change_type: ChangeType
    old_path: str | None = None  # renamed 场景下的旧路径
    additions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "change_type": self.change_type.value,
            "old_path": self.old_path,
            "additions": self.additions,
            "deletions": self.deletions,
        }


@dataclass
class DiffResult:
    """Git Diff 执行结果。"""
    changed_files: list[ChangedFile] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    raw_diff: str = ""

    def to_dict(self) -> dict:
        return {
            "changed_files": [f.to_dict() for f in self.changed_files],
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
        }


class GitTool:
    """基于本地 Git CLI 的差异分析工具。

    通过 `git diff --name-status` 和 `git diff --numstat` 获取两个分支之间的文件变更列表和统计信息。
    前提：用户本地已安装 Git。
    """

    def __init__(self, repo_path: str | Path = "."):
        self.repo_path = Path(repo_path).resolve()

    # ── 公开接口 ──

    def diff(self, target: str = "HEAD", base: str = "main") -> DiffResult:
        """获取 base...target 之间变更文件列表及统计。

        Args:
            target: 目标分支/commit（默认 HEAD）
            base: 基准分支（默认 main）

        Returns:
            DiffResult: 包含 changed_files、total_additions、total_deletions、raw_diff
        """
        self._ensure_repo()

        diff_range = f"{base}...{target}"

        # 获取变更文件名和类型
        name_status = self._run_git(["diff", "--name-status", diff_range])

        # 获取增删行数统计
        numstat = self._run_git(["diff", "--numstat", diff_range])

        # 获取完整 diff 文本
        raw_diff = self._run_git(["diff", diff_range])

        return self._parse(name_status, numstat, raw_diff)

    def diff_file(self, file_path: str, target: str = "HEAD", base: str = "main") -> str:
        """获取单个文件的 diff 内容。"""
        self._ensure_repo()
        diff_range = f"{base}...{target}"
        return self._run_git(["diff", diff_range, "--", file_path])

    def list_branches(self) -> list[str]:
        """列出所有本地分支。"""
        self._ensure_repo()
        output = self._run_git(["branch", "--format=%(refname:short)"])
        return [line.strip() for line in output.splitlines() if line.strip()]

    def current_branch(self) -> str:
        """获取当前分支名。"""
        self._ensure_repo()
        return self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    # ── 内部实现 ──

    def _ensure_repo(self) -> None:
        """验证路径是有效的 Git 仓库。"""
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git(self, args: list[str]) -> str:
        """执行 git 命令并返回 stdout。"""
        cmd = ["git", "-C", str(self.repo_path)] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                # 当 base 分支不存在时给出明确提示
                if "unknown revision" in stderr or "not a git repository" in stderr:
                    raise ValueError(f"Git error: {stderr}")
                # 其他错误（如空仓库）返回空
                return ""
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def _parse(self, name_status: str, numstat: str, raw_diff: str) -> DiffResult:
        """解析 git diff 输出为 DiffResult。"""
        result = DiffResult(raw_diff=raw_diff)

        # 解析 numstat 获取每个文件的增删行数
        stat_map: dict[str, tuple[int, int]] = {}
        for line in numstat.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                add = int(parts[0]) if parts[0] != "-" else 0
                delete = int(parts[1]) if parts[1] != "-" else 0
                # 对于 renamed 文件，格式为: add\tdelete\told_path => new_path
                # 但 numstat 对 rename 用 {old => new} 格式
                file_path = parts[2].strip()
                stat_map[file_path] = (add, delete)

        # 解析 name-status 获取变更类型
        for line in name_status.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status_char = parts[0][0]  # A, M, D, R, C
            rest = "\t".join(parts[1:])

            if status_char == "R":
                # Renamed: R100\told_path\tnew_path
                rename_parts = rest.split("\t")
                if len(rename_parts) >= 2:
                    old_path = rename_parts[0]
                    new_path = rename_parts[1]
                else:
                    old_path = rest
                    new_path = rest
                change_type = ChangeType.RENAMED
                file_path = new_path
                old = old_path
            else:
                file_path = rest
                old = None
                if status_char == "A":
                    change_type = ChangeType.ADDED
                elif status_char == "D":
                    change_type = ChangeType.DELETED
                elif status_char == "M":
                    change_type = ChangeType.MODIFIED
                else:
                    change_type = ChangeType.MODIFIED  # fallback

            # 查找 stat
            add, delete = stat_map.get(file_path, (0, 0))
            result.total_additions += add
            result.total_deletions += delete

            result.changed_files.append(ChangedFile(
                file_path=file_path,
                change_type=change_type,
                old_path=old,
                additions=add,
                deletions=delete,
            ))

        return result
