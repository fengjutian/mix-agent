"""MCP 服务器配置持久化存储 — JSON 文件读写。"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


_DEFAULT_PATH = Path("mcp_servers.json")

TransportKind = Literal["stdio", "http", "sse"]


@dataclass
class MCPServerConfig:
    """单个 MCP 服务器配置。"""
    name: str
    transport: TransportKind = "stdio"
    enabled: bool = True

    # stdio
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # http / sse
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "transport": self.transport,
            "enabled": self.enabled,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "headers": self.headers,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MCPServerConfig:
        return cls(
            name=d.get("name", ""),
            transport=d.get("transport", "stdio"),
            enabled=d.get("enabled", True),
            command=d.get("command", ""),
            args=d.get("args", []),
            env=d.get("env", {}),
            url=d.get("url", ""),
            headers=d.get("headers", {}),
        )


class MCPServerStore:
    """MCP 服务器配置 JSON 文件存储。"""

    def __init__(self, path: Path | str = _DEFAULT_PATH):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._servers: dict[str, MCPServerConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    cfg = MCPServerConfig.from_dict(item)
                    if cfg.name:
                        self._servers[cfg.name] = cfg
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                [s.to_dict() for s in self._servers.values()],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ── CRUD ──

    def list_all(self) -> list[MCPServerConfig]:
        with self._lock:
            return list(self._servers.values())

    def get(self, name: str) -> MCPServerConfig | None:
        with self._lock:
            return self._servers.get(name)

    def add(self, cfg: MCPServerConfig) -> bool:
        """添加新的 MCP 服务器配置。"""
        if not cfg.name:
            return False
        with self._lock:
            if cfg.name in self._servers:
                return False
            self._servers[cfg.name] = cfg
            self._save()
        return True

    def update(self, name: str, updates: dict) -> bool:
        """更新指定 MCP 服务器配置（部分更新）。"""
        with self._lock:
            cfg = self._servers.get(name)
            if not cfg:
                return False
            for key, value in updates.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
            self._save()
        return True

    def delete(self, name: str) -> bool:
        with self._lock:
            if name not in self._servers:
                return False
            del self._servers[name]
            self._save()
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        return self.update(name, {"enabled": enabled})


# 全局单例
mcp_store = MCPServerStore()
