"""LLM 调用封装 — 统一 MiniMax + DeepSeek（OpenAI 兼容接口）的异步调用、指数退避重试与成本追踪。"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from mix_agent.config import settings


# ══════════════════════════════════════════
# 模型注册表
# ══════════════════════════════════════════

@dataclass
class ModelSpec:
    provider: str                        # "minimax" | "deepseek"
    model: str
    base_url: str
    api_key: str
    # 定价（每百万 token，USD）
    input_price_per_m: float = 0.0       # $/1M prompt tokens
    output_price_per_m: float = 0.0      # $/1M completion tokens


MODEL_REGISTRY: dict[str, ModelSpec] = {}


def _register():
    """从 settings 加载已配置的模型。"""
    if settings.MINIMAX_API_KEY:
        MODEL_REGISTRY["minimax"] = ModelSpec(
            provider="minimax",
            model=settings.MINIMAX_MODEL,
            base_url=settings.MINIMAX_BASE_URL,
            api_key=settings.MINIMAX_API_KEY,
            input_price_per_m=0.20,     # MiniMax 参考定价
            output_price_per_m=0.80,
        )
    if settings.DEEPSEEK_API_KEY:
        MODEL_REGISTRY["deepseek"] = ModelSpec(
            provider="deepseek",
            model=settings.DEEPSEEK_MODEL,
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            input_price_per_m=0.14,     # DeepSeek 参考定价
            output_price_per_m=0.28,
        )

_register()


# ══════════════════════════════════════════
# 调用结果
# ══════════════════════════════════════════

@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    latency_ms: int = 0


@dataclass
class CostTracker:
    """跨调用累加成本。"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    calls: int = 0

    def record(self, resp: LLMResponse) -> None:
        self.total_prompt_tokens += resp.prompt_tokens
        self.total_completion_tokens += resp.completion_tokens
        self.total_cost += resp.cost
        self.calls += 1

    @property
    def budget_exceeded(self) -> bool:
        # 硬上限 $5.0；可配置化
        return self.total_cost >= 5.0

    @property
    def budget_warning(self) -> bool:
        # 80% 降级阈值
        return self.total_cost >= 4.0


# ══════════════════════════════════════════
# LLM 客户端
# ══════════════════════════════════════════

class LLMClient:
    """统一 LLM 调用客户端。

    支持 MiniMax 和 DeepSeek（均为 OpenAI 兼容的 /v1/chat/completions 接口）。
    内置指数退避重试、Jitter 防抖、成本追踪。
    """

    MAX_RETRIES: int = 3
    BASE_DELAY: float = 1.0          # 初始退避 1s
    MAX_DELAY: float = 30.0           # 退避上限
    REQUEST_TIMEOUT: float = 120.0
    RATE_LIMIT_STATUS: int = 429

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── 公开 API ──

    async def chat(
        self,
        provider: str,                  # "minimax" | "deepseek"
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        cost_tracker: CostTracker | None = None,
        override_model: str | None = None,
    ) -> LLMResponse:
        """发送聊天请求，自动重试。

        Args:
            provider: 模型提供商标识 ("minimax" | "deepseek")
            messages: OpenAI 格式的消息列表 [{"role":"...","content":"..."}]
            temperature: 生成温度（默认 0.3，审计场景偏保守）
            max_tokens: 最大生成 token 数
            cost_tracker: 可选的 CostTracker，用于跨调用累加成本
            override_model: 覆盖默认模型名（用于降级场景）

        Returns:
            LLMResponse: 含 content / tokens / cost / latency

        Raises:
            RuntimeError: 所有重试均失败
        """
        spec = MODEL_REGISTRY.get(provider)
        if spec is None:
            known = list(MODEL_REGISTRY.keys())
            raise ValueError(f"Unknown provider '{provider}'. Known: {known}")

        model = override_model or spec.model
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await self._call(
                    spec=spec,
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    cost_tracker=cost_tracker,
                )
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == self.RATE_LIMIT_STATUS and attempt < self.MAX_RETRIES:
                    delay = min(
                        self.BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                        self.MAX_DELAY,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise RuntimeError(f"LLM HTTP {e.response.status_code}: {e.response.text[:500]}") from e
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.BASE_DELAY * (2 ** attempt))
                    continue
                raise RuntimeError(f"LLM request timed out after {self.MAX_RETRIES+1} attempts") from e
            except httpx.RequestError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.BASE_DELAY)
                    continue
                raise RuntimeError(f"LLM request failed: {e}") from e

        raise RuntimeError(f"All retries exhausted: {last_error}")

    async def chat_with_prompt(
        self,
        provider: str,
        system_prompt: str,
        user_message: str,
        **kwargs,
    ) -> LLMResponse:
        """便捷方法：自动拼接 system + user 消息。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.chat(provider, messages, **kwargs)

    def list_providers(self) -> list[str]:
        return list(MODEL_REGISTRY.keys())

    # ── 内部实现 ──

    async def _call(
        self,
        spec: ModelSpec,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        cost_tracker: CostTracker | None,
    ) -> LLMResponse:
        t0 = time.monotonic()
        client = await self._get_client()

        url = f"{spec.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {spec.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # 计算成本
        cost = (
            (prompt_tokens / 1_000_000) * spec.input_price_per_m
            + (completion_tokens / 1_000_000) * spec.output_price_per_m
        )

        choice = data["choices"][0]
        content = choice["message"]["content"]

        latency = int((time.monotonic() - t0) * 1000)

        result = LLMResponse(
            content=content,
            model=model,
            provider=spec.provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            latency_ms=latency,
        )

        if cost_tracker:
            cost_tracker.record(result)

        return result


# 单例
llm_client = LLMClient()
