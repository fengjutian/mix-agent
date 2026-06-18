"""集中式节点→模型映射 — 所有 agent 节点从此读取 provider，支持运行时覆盖。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# ══════════════════════════════════════════
# 节点默认配置（硬编码兜底）
# ══════════════════════════════════════════

DEFAULT_NODE_PROVIDERS: dict[str, str] = {
    "parse_requirement":  "minimax",
    "orchestrator":       "deepseek",
    "code_review":        "deepseek",
    "sql_risk_explain":   "deepseek",
    "summary":            "deepseek",
    "api_path":           "deepseek",
    "auto_fix":           "deepseek",
    "compliance":         "deepseek",
}

# 运行时覆盖（PUT /admin/models/assign 写入）
_overrides: dict[str, str] = {}
_lock = threading.Lock()


def get_provider(node_name: str) -> str:
    """返回指定节点的 provider。
    
    优先取运行时覆盖，否则取默认值。若都不存在则返回 "deepseek"。
    """
    with _lock:
        return _overrides.get(node_name) or DEFAULT_NODE_PROVIDERS.get(node_name, "deepseek")


def set_node_provider(node_name: str, provider: str) -> bool:
    """设置节点的 provider（运行时覆盖）。
    
    Returns:
        True 表示成功，False 表示节点名无效。
    """
    if node_name not in DEFAULT_NODE_PROVIDERS:
        return False
    with _lock:
        _overrides[node_name] = provider
    return True


def list_nodes() -> list[dict]:
    """列出所有节点及其当前 provider 配置。"""
    from mix_agent.services.llm import MODEL_REGISTRY

    nodes = []
    for name in DEFAULT_NODE_PROVIDERS:
        provider = get_provider(name)
        model_spec = MODEL_REGISTRY.get(provider)
        nodes.append({
            "node": name,
            "provider": provider,
            "model": model_spec.model if model_spec else "unknown",
            "overridden": name in _overrides,
        })
    return nodes


def list_models() -> list[dict]:
    """列出所有已注册的模型（隐藏 API key）。"""
    from mix_agent.services.llm import MODEL_REGISTRY

    models = []
    for key, spec in MODEL_REGISTRY.items():
        models.append({
            "provider": spec.provider,
            "model": spec.model,
            "base_url": spec.base_url,
            "input_price_per_m": spec.input_price_per_m,
            "output_price_per_m": spec.output_price_per_m,
        })
    return models
