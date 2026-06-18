"""依赖注入模块 — Redis/Qdrant 客户端。"""

from __future__ import annotations

from typing import AsyncGenerator

from qdrant_client import QdrantClient
from redis.asyncio import Redis

from mix_agent.config import settings

# ── Redis / Qdrant ──


async def get_redis() -> AsyncGenerator[Redis, None]:
    """注入 Redis 异步连接。"""
    r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield r
    finally:
        await r.aclose()


def get_qdrant() -> QdrantClient:
    """注入 Qdrant 同步客户端。"""
    return QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY or None,
    )
