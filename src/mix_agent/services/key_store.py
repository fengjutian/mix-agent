"""API Key 文件持久化存储 — 读写 config/provider_keys.json，支持运行时更新并重新注册模型。"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# 配置文件路径（相对于项目根目录）
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"
KEYS_FILE = CONFIG_DIR / "provider_keys.json"

_lock = threading.Lock()


@dataclass
class ProviderKeyEntry:
    provider: str
    api_key: str          # 明文 key（仅内存中）
    base_url: str
    model: str


def _ensure_file() -> None:
    """确保配置文件存在。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not KEYS_FILE.exists():
        KEYS_FILE.write_text(json.dumps({}, indent=2), encoding="utf-8")


def load_keys() -> dict[str, ProviderKeyEntry]:
    """从 JSON 文件加载所有 provider key 配置。"""
    _ensure_file()
    with _lock:
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            data = {}

    result: dict[str, ProviderKeyEntry] = {}
    for provider, entry in data.items():
        if isinstance(entry, dict) and entry.get("api_key"):
            result[provider] = ProviderKeyEntry(
                provider=provider,
                api_key=entry["api_key"],
                base_url=entry.get("base_url", ""),
                model=entry.get("model", ""),
            )
    return result


def list_keys() -> list[dict]:
    """列出所有已配置的 provider key（隐藏明文 key，仅显示前/后几位）。"""
    _ensure_file()
    with _lock:
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            data = {}

    result = []
    for provider, entry in data.items():
        if not isinstance(entry, dict):
            continue
        api_key = entry.get("api_key", "")
        masked = _mask_key(api_key)
        result.append({
            "provider": provider,
            "api_key_masked": masked,
            "has_key": bool(api_key),
            "base_url": entry.get("base_url", ""),
            "model": entry.get("model", ""),
        })
    return result


def set_key(provider: str, api_key: str, base_url: str = "", model: str = "") -> bool:
    """设置或更新某个 provider 的 API key。返回 True 表示成功。"""
    _ensure_file()
    provider = provider.strip().lower()
    if not provider:
        return False

    with _lock:
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            data = {}

        if provider not in data:
            data[provider] = {}

        if api_key:
            data[provider]["api_key"] = api_key
        if base_url:
            data[provider]["base_url"] = base_url
        if model:
            data[provider]["model"] = model

        KEYS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 重新注册模型
    _reload_registry()
    return True


def delete_key(provider: str) -> bool:
    """删除某个 provider 的 API key 配置。返回 True 表示成功。"""
    _ensure_file()
    provider = provider.strip().lower()
    with _lock:
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return False

        if provider not in data:
            return False

        del data[provider]
        KEYS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _reload_registry()
    return True


def _mask_key(key: str) -> str:
    """遮盖 API key，仅显示前 4 位和后 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _reload_registry() -> None:
    """重新注册模型到 MODEL_REGISTRY（合并 env 配置与文件配置）。"""
    from mix_agent.services.llm import MODEL_REGISTRY, ModelSpec
    from mix_agent.config import settings

    # 清除现有注册（保留 env 注入的重新加载）
    MODEL_REGISTRY.clear()

    # 1) 从环境变量加载
    if settings.MINIMAX_API_KEY:
        MODEL_REGISTRY["minimax"] = ModelSpec(
            provider="minimax",
            model=settings.MINIMAX_MODEL,
            base_url=settings.MINIMAX_BASE_URL,
            api_key=settings.MINIMAX_API_KEY,
            input_price_per_m=0.20,
            output_price_per_m=0.80,
        )
    if settings.DEEPSEEK_API_KEY:
        MODEL_REGISTRY["deepseek"] = ModelSpec(
            provider="deepseek",
            model=settings.DEEPSEEK_MODEL,
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            input_price_per_m=0.14,
            output_price_per_m=0.28,
        )

    # 2) 从配置文件加载（文件中的 key 会覆盖/补充 env 中未配置的）
    file_keys = load_keys()
    for provider, entry in file_keys.items():
        # 暂时为未知 provider 使用默认定价
        MODEL_REGISTRY[provider] = ModelSpec(
            provider=provider,
            model=entry.model or "unknown",
            base_url=entry.base_url or "",
            api_key=entry.api_key,
            input_price_per_m=0.20,
            output_price_per_m=0.80,
        )
