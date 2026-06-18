"""Prompt 持久化存储 — JSON 文件读写，重启不丢失。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from mix_agent.agents.prompts import PROMPTS, PromptTemplate


_DEFAULT_PATH = Path("prompts.json")
_CUSTOM_PATH = Path("custom_prompts.json")


class PromptStore:
    """Prompt JSON 文件存储。

    - 内置 PROMPTS 作为默认值
    - prompts.json 中的值覆盖默认值
    - custom_prompts.json 存放用户新建的 prompt
    - 写入时保存到 JSON 文件
    """

    def __init__(self, path: Path | str = _DEFAULT_PATH, custom_path: Path | str = _CUSTOM_PATH):
        self._path = Path(path)
        self._custom_path = Path(custom_path)
        self._lock = threading.Lock()
        self._overrides: dict[str, dict[str, str]] = {}
        self._custom: dict[str, dict[str, str]] = {}
        self._load()
        self._load_custom()

    # ── file I/O ──

    def _load(self) -> None:
        """从 JSON 文件加载覆盖值。"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for agent, fields in data.items():
                    if agent in PROMPTS and isinstance(fields, dict):
                        self._overrides[agent] = {
                            k: v for k, v in fields.items() if isinstance(v, str)
                        }
        except (json.JSONDecodeError, OSError):
            pass

    def _load_custom(self) -> None:
        """从 custom_prompts.json 加载用户创建的 prompt。"""
        if not self._custom_path.exists():
            return
        try:
            data = json.loads(self._custom_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for agent, fields in data.items():
                    if isinstance(fields, dict) and "system" in fields:
                        self._custom[agent] = {
                            "system": fields.get("system", ""),
                            "user_template": fields.get("user_template", "{input}"),
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

    def _save_custom(self) -> None:
        """写入自定义 prompts JSON 文件。"""
        self._custom_path.parent.mkdir(parents=True, exist_ok=True)
        self._custom_path.write_text(
            json.dumps(self._custom, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── public API ──

    def get(self, agent: str) -> PromptTemplate:
        """获取 agent 的当前 prompt（覆盖 + 默认合并，或自定义）。"""
        # 先检查自定义
        if agent in self._custom:
            c = self._custom[agent]
            return PromptTemplate(
                agent=agent,
                system=c["system"],
                user_template=c.get("user_template", "{input}"),
            )
        # 再检查内置
        base = PROMPTS[agent]  # KeyError if unknown agent
        override = self._overrides.get(agent, {})
        return PromptTemplate(
            agent=agent,
            system=override.get("system", base.system),
            user_template=override.get("user_template", base.user_template),
        )

    def list_all(self) -> list[dict]:
        """列出所有 agent 的当前 prompt（内置 + 自定义）。"""
        result = []
        # 内置 agents
        for agent in PROMPTS:
            pt = self.get(agent)
            result.append({
                "agent": agent,
                "system": pt.system,
                "user_template": pt.user_template,
                "overridden": agent in self._overrides,
                "is_custom": False,
            })
        # 自定义 agents
        for agent, fields in self._custom.items():
            result.append({
                "agent": agent,
                "system": fields.get("system", ""),
                "user_template": fields.get("user_template", "{input}"),
                "overridden": False,
                "is_custom": True,
            })
        return result

    def add(self, agent: str, system: str, user_template: str = "{input}") -> bool:
        """创建新的自定义 prompt。

        Args:
            agent: 唯一标识符
            system: system prompt 内容
            user_template: user template（默认 "{input}"）

        Returns:
            True 成功，False 名称已存在或为空
        """
        agent = agent.strip()
        if not agent:
            return False
        if agent in PROMPTS or agent in self._custom:
            return False

        with self._lock:
            self._custom[agent] = {
                "system": system,
                "user_template": user_template,
            }
            self._save_custom()
        return True

    def update(self, agent: str, system: str | None = None, user_template: str | None = None) -> bool:
        """更新指定 agent 的 prompt 并持久化。

        Args:
            agent: agent 名称
            system: 新的 system prompt（None 表示不修改）
            user_template: 新的 user_template（None 表示不修改）

        Returns:
            True 成功，False agent 不存在
        """
        with self._lock:
            if agent in self._custom:
                if system is not None:
                    self._custom[agent]["system"] = system
                if user_template is not None:
                    self._custom[agent]["user_template"] = user_template
                self._save_custom()
                return True

            if agent not in PROMPTS:
                return False

            entry = self._overrides.get(agent, {})
            if system is not None:
                entry["system"] = system
            if user_template is not None:
                entry["user_template"] = user_template
            self._overrides[agent] = entry
            self._save()
        return True

    def delete(self, agent: str) -> bool:
        """删除指定 agent 的 prompt。

        - 自定义 agent：从 custom_prompts.json 中彻底移除
        - 内置 agent：移除覆盖值（等同重置为默认）

        Returns:
            True 成功，False agent 不存在
        """
        with self._lock:
            if agent in self._custom:
                del self._custom[agent]
                self._save_custom()
                return True
            if agent in PROMPTS:
                if agent in self._overrides:
                    del self._overrides[agent]
                    self._save()
                return True
            return False

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
