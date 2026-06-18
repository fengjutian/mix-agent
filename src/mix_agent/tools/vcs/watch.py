"""Watch Mode 服务 — 监听文件变更并自动触发审计。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from mix_agent.tools.vcs.git_tool import GitTool, ChangeType


class WatchMode:
    """文件系统监听 → 自动 diff → 触发审计回调。

    使用 polling 方式检查文件修改时间（跨平台兼容），
    配合 Tauri 的 notify crate 实现原生文件监听。
    """

    def __init__(
        self,
        repo_path: str | Path = ".",
        poll_interval: float = 2.0,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.poll_interval = poll_interval
        self._git = GitTool(str(self.repo_path))
        self._last_mtimes: dict[str, float] = {}
        self._callbacks: list[Callable] = []
        self._running = False

    # ── 公开 API ──

    def on_change(self, callback: Callable) -> None:
        """注册文件变更回调。callback 接收 changed_files 列表。"""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """启动监听循环。"""
        self._running = True
        self._snapshot()  # 初始快照

        while self._running:
            changed = self._check_changes()
            if changed:
                # 通知所有回调
                for cb in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(changed)
                        else:
                            cb(changed)
                    except Exception:
                        pass  # 回调异常不影响监听

            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        """停止监听。"""
        self._running = False

    # ── 内部实现 ──

    def _snapshot(self) -> None:
        """记录当前所有文件的修改时间。"""
        self._last_mtimes.clear()
        for fp in self.repo_path.rglob("*"):
            if fp.is_file() and self._should_watch(fp):
                try:
                    self._last_mtimes[str(fp)] = fp.stat().st_mtime
                except OSError:
                    pass

    def _check_changes(self) -> list[str]:
        """检查自上次快照以来变更的文件。返回变更文件路径列表。"""
        changed: list[str] = []

        for fp in self.repo_path.rglob("*"):
            if not fp.is_file() or not self._should_watch(fp):
                continue
            key = str(fp)
            try:
                mtime = fp.stat().st_mtime
            except OSError:
                continue

            if key not in self._last_mtimes:
                changed.append(key)
            elif mtime != self._last_mtimes[key]:
                changed.append(key)

            self._last_mtimes[key] = mtime

        return changed

    def _should_watch(self, path: Path) -> bool:
        """判断是否应监听该文件。"""
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".mix-agent-backups"}
        for part in path.parts:
            if part in skip_dirs:
                return False
        # 忽略 .bak 文件
        if path.suffix == ".bak":
            return False
        return True
