"""依赖注入模块 — 提供 Qdrant 客户端、Redis 缓存的 FastAPI 依赖项。"""

from typing import AsyncGenerator

from fastapi import Depends
from redis.asyncio import Redis
from qdrant_client import QdrantClient

from mix_agent.config import settings


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
