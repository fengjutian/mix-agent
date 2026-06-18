"""Prompt 持久化存储 — JSON 文件读写，重启不丢失。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from mix_agent.agents.prompts import PROMPTS, PromptTemplate


_DEFAULT_PATH = Path("prompts.json")


class PromptStore:
    """Prompt JSON 文件存储。

    - 内置 PROMPTS 作为默认值
    - prompts.json 中的值覆盖默认值
    - 写入时保存到 JSON 文件
    """

    def __init__(self, path: Path | str = _DEFAULT_PATH):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._overrides: dict[str, dict[str, str]] = {}
        self._load()

    # ── file I/O ──

    def _load(self) -> None:
        """从 JSON 文件加载覆盖值。"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # 只保留与内置 prompts 键匹配的 agent
                for agent, fields in data.items():
                    if agent in PROMPTS and isinstance(fields, dict):
                        self._overrides[agent] = {
                            k: v for k, v in fields.items() if isinstance(v, str)
                        }
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        """写入 JSON 文件（只写有覆盖值的 agent）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._overrides, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── public API ──

    def get(self, agent: str) -> PromptTemplate:
        """获取 agent 的当前 prompt（覆盖 + 默认合并）。"""
        base = PROMPTS[agent]  # KeyError if unknown agent
        override = self._overrides.get(agent, {})
        return PromptTemplate(
            agent=agent,
            system=override.get("system", base.system),
            user_template=override.get("user_template", base.user_template),
        )

    def list_all(self) -> list[dict]:
        """列出所有 agent 的当前 prompt。"""
        result = []
        for agent in PROMPTS:
            pt = self.get(agent)
            result.append({
                "agent": agent,
                "system": pt.system,
                "user_template": pt.user_template,
                "overridden": agent in self._overrides,
            })
        return result

    def update(self, agent: str, system: str | None = None, user_template: str | None = None) -> bool:
        """更新指定 agent 的 prompt 并持久化。

        Args:
            agent: agent 名称
            system: 新的 system prompt（None 表示不修改）
            user_template: 新的 user_template（None 表示不修改）

        Returns:
            True 成功，False agent 不存在
        """
        if agent not in PROMPTS:
            return False

        with self._lock:
            entry = self._overrides.get(agent, {})
            if system is not None:
                entry["system"] = system
            if user_template is not None:
                entry["user_template"] = user_template
            self._overrides[agent] = entry
            self._save()
        return True

    def reset(self, agent: str) -> bool:
        """重置指定 agent 的 prompt 为内置默认值。"""
        if agent not in PROMPTS:
            return False
        with self._lock:
            self._overrides.pop(agent, None)
            self._save()
        return True


# 全局单例
prompt_store = PromptStore()
