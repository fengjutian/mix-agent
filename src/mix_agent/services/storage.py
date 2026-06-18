"""Redis 缓存管理器 — 托管 LangGraph 历史 Session 快照与分布式 Token 熔断计数器。"""

from redis.asyncio import Redis


class StorageService:
    """Redis 缓存服务。

    职责：
    - LangGraph Session 快照持久化
    - 分布式 Token 熔断计数器
    - 任务状态缓存
    """

    def __init__(self, redis: Redis):
        self._redis = redis

    async def save_session(self, session_id: str, data: dict) -> None:
        """保存 LangGraph 会话快照。"""
        await self._redis.set(f"session:{session_id}", str(data))

    async def load_session(self, session_id: str) -> dict | None:
        """加载 LangGraph 会话快照。"""
        data = await self._redis.get(f"session:{session_id}")
        return None if data is None else eval(data)  # noqa: S307 — 原型阶段

    async def delete_session(self, session_id: str) -> None:
        """删除会话快照。"""
        await self._redis.delete(f"session:{session_id}")

    # ─── Token 熔断计数器 ───

    async def get_token_usage(self, key: str) -> int:
        """获取当前 Token 消耗计数。"""
        val = await self._redis.get(f"token:{key}")
        return int(val) if val else 0

    async def increment_token_usage(self, key: str, amount: int, ttl: int = 60) -> int:
        """增加 Token 消耗计数（带 TTL）。"""
        pipe = self._redis.pipeline()
        pipe.incrby(f"token:{key}", amount)
        pipe.expire(f"token:{key}", ttl)
        result, _ = await pipe.execute()
        return result
