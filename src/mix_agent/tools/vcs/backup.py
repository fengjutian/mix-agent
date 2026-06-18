"""文件备份与回滚服务 — 修改前自动备份，支持 .bak 和 git stash 两种策略。"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class BackupEntry:
    """单条备份记录。"""
    file_path: str
    backup_path: str
    strategy: str  # "bak" | "git_stash"
    created_at: str
    restored: bool = False


@dataclass
class BackupResult:
    """备份操作结果。"""
    entries: list[BackupEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.entries)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class FileBackupManager:
    """文件备份管理器。

    两种策略：
    1. .bak — 复制文件为 .bak 后缀（简单快速）
    2. git stash — 用 git stash push 暂存未提交变更（安全可靠）

    回滚时按策略反向恢复。
    """

    BACKUP_DIR_NAME = ".mix-agent-backups"

    def __init__(self, repo_path: str | Path = "."):
        self.repo_path = Path(repo_path).resolve()
        self.backup_dir = self.repo_path / self.BACKUP_DIR_NAME
        self._entries: list[BackupEntry] = []

    # ── 备份 ──

    def backup_file(self, file_path: str | Path, strategy: str = "bak") -> BackupEntry | None:
        """备份单个文件。"""
        src = (self.repo_path / file_path).resolve()
        if not src.exists():
            return None

        now = datetime.now().isoformat()
        entry: BackupEntry | None = None

        if strategy == "bak":
            entry = self._backup_bak(src, now)
        elif strategy == "git_stash":
            entry = self._backup_git_stash(str(file_path), now)

        if entry:
            self._entries.append(entry)

        return entry

    def backup_files(self, file_paths: list[str], strategy: str = "bak") -> BackupResult:
        """批量备份文件。"""
        result = BackupResult()
        for fp in file_paths:
            try:
                entry = self.backup_file(fp, strategy)
                if entry:
                    result.entries.append(entry)
            except Exception as e:
                result.errors.append(f"{fp}: {e}")
        return result

    # ── 回滚 ──

    def rollback_file(self, entry: BackupEntry) -> bool:
        """根据备份记录回滚文件。"""
        if entry.restored:
            return False

        src = self.repo_path / entry.file_path

        if entry.strategy == "bak":
            backup = Path(entry.backup_path)
            if backup.exists():
                shutil.copy2(backup, src)
                backup.unlink()
                entry.restored = True
                return True

        elif entry.strategy == "git_stash":
            try:
                subprocess.run(
                    ["git", "-C", str(self.repo_path), "stash", "pop"],
                    capture_output=True, timeout=10,
                )
                entry.restored = True
                return True
            except Exception:
                pass

        return False

    def rollback_all(self) -> int:
        """回滚所有备份。返回成功数。"""
        count = 0
        for entry in self._entries:
            if self.rollback_file(entry):
                count += 1
        return count

    def list_backups(self) -> list[BackupEntry]:
        return list(self._entries)

    # ── 清理 ──

    def cleanup(self) -> int:
        """清理所有 .bak 备份文件和备份目录。"""
        count = 0
        # 清理 .bak 文件
        for entry in self._entries:
            if entry.strategy == "bak":
                bak_path = Path(entry.backup_path)
                if bak_path.exists():
                    bak_path.unlink()
                    count += 1

        # 清理备份目录
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)

        self._entries.clear()
        return count

    # ── 内部实现 ──

    def _backup_bak(self, src: Path, timestamp: str) -> BackupEntry:
        """.bak 策略：复制文件为 .bak 后缀。"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        rel_path = src.relative_to(self.repo_path)
        safe_name = str(rel_path).replace("/", "_").replace("\\", "_")
        backup_path = self.backup_dir / f"{safe_name}.{timestamp}.bak"

        shutil.copy2(src, backup_path)

        return BackupEntry(
            file_path=str(rel_path),
            backup_path=str(backup_path),
            strategy="bak",
            created_at=timestamp,
        )

    def _backup_git_stash(self, file_path: str, timestamp: str) -> BackupEntry:
        """git stash 策略：stash 该文件的变更。"""
        try:
            subprocess.run(
                ["git", "-C", str(self.repo_path), "stash", "push", "--", file_path],
                capture_output=True, timeout=10, check=True,
            )
        except subprocess.CalledProcessError:
            # 文件可能无变更，stash 会失败 — 忽略
            pass

        return BackupEntry(
            file_path=file_path,
            backup_path=f"git:stash@{timestamp}",
            strategy="git_stash",
            created_at=timestamp,
        )
