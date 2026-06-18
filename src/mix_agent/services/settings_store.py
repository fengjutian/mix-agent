"""全局应用设置持久化存储 — JSON 文件读写，重启不丢失。"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from mix_agent.schemas import GlobalSettingsSchema

_SETTINGS_PATH = Path("settings.json")

DEFAULTS = GlobalSettingsSchema()


class SettingsStore:
    """全局应用设置 JSON 文件存储。

    职责：
    - 使用 settings.json 持久化所有设置项
    - 缺失时自动回退到 GlobalSettingsSchema 默认值
    - 线程安全
    """

    def __init__(self, path: Path | str = _SETTINGS_PATH):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict = {}
        self._updated_at: str | None = None
        self._load()

    # ── file I/O ──

    def _load(self) -> None:
        """从 JSON 文件加载设置。"""
        if not self._path.exists():
            return
        try:
            with self._lock:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = raw.get("data", {}) if isinstance(raw.get("data"), dict) else {}
                self._updated_at = raw.get("updated_at")
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        """将当前设置写入 JSON 文件。"""
        with self._lock:
            self._updated_at = datetime.now(timezone.utc).isoformat()
            payload = {
                "data": self._data,
                "updated_at": self._updated_at,
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── API ──

    def get_all(self) -> dict:
        """获取所有设置项（合并默认值）。"""
        defaults = DEFAULTS.model_dump()
        merged = {**defaults, **{k: v for k, v in self._data.items() if v is not None}}
        return {
            "data": GlobalSettingsSchema(**merged).model_dump(),
            "updated_at": self._updated_at,
        }

    def update(self, updates: dict) -> dict:
        """部分更新设置项。

        Example: update({"sandbox_timeout": 60, "sqlguard_enabled": False})
        """
        # 只保留已知字段
        allowed = set(GlobalSettingsSchema.model_fields.keys())
        for key, value in updates.items():
            if key in allowed:
                self._data[key] = value

        self._save()
        return self.get_all()


# 单例
settings_store = SettingsStore()
