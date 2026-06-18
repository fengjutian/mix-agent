"""依赖注入模块 — Redis/Qdrant 客户端 + JWT 认证中间件。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


# ── JWT 认证 ──

security = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


def create_access_token(user_id: str, username: str, role: str) -> str:
    """签发 JWT access token。"""
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT token，无效时抛异常。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """从 Authorization header 提取当前用户信息。"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = decode_token(credentials.credentials)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_role(*roles: str):
    """角色校验依赖项工厂。"""

    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _check


# 预定义角色校验器
require_admin = require_role("admin")
require_auditor = require_role("auditor", "admin")
require_developer = require_role("developer", "auditor", "admin")
