"""API 鉴权中间件 — 可选的 API Key / Bearer Token 验证。

开发环境默认关闭（ALLOW_NO_AUTH=true），生产环境通过环境变量启用。
"""

from __future__ import annotations

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from mix_agent.config import settings


# 不需要鉴权的路径前缀
PUBLIC_PATHS: set[str] = {
    "/health",
    "/openapi.json",
    "/docs",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """简单的 Bearer Token 鉴权中间件。

    验证逻辑：
    1. 如果 PUBLIC_PATHS 匹配 → 放行
    2. 如果 API_AUTH_TOKEN 未配置 → 放行（开发模式）
    3. 否则验证 Authorization: Bearer <token> 头
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 公开路径放行
        for public in PUBLIC_PATHS:
            if path == public or path.startswith(public):
                return await call_next(request)

        # 未配置 token 时放行（向后兼容，不破坏现有测试）
        if not settings.API_AUTH_TOKEN:
            return await call_next(request)

        # 验证 token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

        token = auth_header[7:]
        if token != settings.API_AUTH_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid API token")

        return await call_next(request)
