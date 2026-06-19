"""HTTP 代理端点 — 类似 Postman，前端通过此后端代理发送任意 HTTP 请求。

安全说明：
- 该端点默认启用，允许前端代理任意 HTTP 请求
- 如需禁用，设置环境变量 ENABLE_PROXY=false
- 所有请求经过 AuthMiddleware 鉴权
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mix_agent.config import settings

router = APIRouter()

# ── 请求模型 ──


class ProxyRequest(BaseModel):
    """HTTP 代理请求体。"""
    method: str = Field(default="GET", description="HTTP 方法 (GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS)")
    url: str = Field(..., min_length=1, description="目标 URL (含协议)")
    headers: dict[str, str] = Field(default_factory=dict, description="请求头键值对")
    query_params: dict[str, str] = Field(default_factory=dict, description="查询参数键值对")
    body: str | None = Field(default=None, description="请求体 (原始字符串)")
    content_type: str | None = Field(default=None, description="Content-Type 头，优先级高于 headers 中的设置")
    timeout_seconds: int = Field(default=30, ge=1, le=120, description="超时时间（秒）")


class ProxyResponse(BaseModel):
    """HTTP 代理响应体。"""
    ok: bool = True
    status: int = 0
    status_text: str = ""
    headers: dict[str, str] = {}
    body: str = ""
    timing_ms: float = 0
    error: str = ""


# ── 端点 ──


@router.post("/proxy", response_model=ProxyResponse)
async def proxy_request(req: ProxyRequest) -> ProxyResponse:
    """代理发送 HTTP 请求并返回响应。

    Args:
        req: 代理请求配置

    Returns:
        ProxyResponse: 包含状态码、响应头、响应体和耗时
    """
    # 检查是否启用
    if not getattr(settings, "ENABLE_PROXY", True):
        raise HTTPException(status_code=403, detail="代理功能已禁用 (ENABLE_PROXY=false)")

    method = req.method.upper()
    if method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}:
        return ProxyResponse(ok=False, error=f"不支持的 HTTP 方法: {req.method}")

    # 构建请求头
    headers: dict[str, str] = dict(req.headers)
    if req.content_type:
        headers["content-type"] = req.content_type

    # 构建 URL（附加查询参数）
    url = req.url
    if req.query_params:
        from urllib.parse import urlencode, urlparse, urlunparse
        parsed = urlparse(url)
        existing_params: dict[str, list[str]] = {}
        if parsed.query:
            from urllib.parse import parse_qs
            existing_params = parse_qs(parsed.query)
        # 合并查询参数（用户传入的优先）
        merged: dict[str, list[str]] = {}
        for k, vs in existing_params.items():
            merged[k] = vs
        for k, v in req.query_params.items():
            merged[k] = [v]
        # 重新编码
        new_query = urlencode(merged, doseq=True)
        url = urlunparse(parsed._replace(query=new_query))

    t0 = time.perf_counter()
    content: str = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(req.timeout_seconds)) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=req.body.encode("utf-8") if req.body else None,
                follow_redirects=True,
            )
            timing_ms = (time.perf_counter() - t0) * 1000

            # 尝试解码响应体
            try:
                content = response.text
            except Exception:
                # 二进制内容用 base64 编码返回
                import base64
                content = f"[binary:{base64.b64encode(response.content).decode('ascii')}]"

            return ProxyResponse(
                ok=True,
                status=response.status_code,
                status_text=response.reason_phrase or "",
                headers=dict(response.headers),
                body=content,
                timing_ms=round(timing_ms, 1),
            )

    except httpx.TimeoutException:
        timing_ms = (time.perf_counter() - t0) * 1000
        return ProxyResponse(
            ok=False,
            error=f"请求超时 ({req.timeout_seconds}s)",
            timing_ms=round(timing_ms, 1),
        )
    except httpx.ConnectError as e:
        timing_ms = (time.perf_counter() - t0) * 1000
        return ProxyResponse(
            ok=False,
            error=f"连接失败: {e}",
            timing_ms=round(timing_ms, 1),
        )
    except Exception as e:
        timing_ms = (time.perf_counter() - t0) * 1000
        return ProxyResponse(
            ok=False,
            error=f"请求异常: {e}",
            timing_ms=round(timing_ms, 1),
        )
