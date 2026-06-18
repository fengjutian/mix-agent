"""认证 API — JWT 登录与 Token 刷新。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from mix_agent.api.deps import create_access_token, decode_token

router = APIRouter()


# ── 请求/响应模型 ──


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


# ── 模拟用户存储（生产环境替换为 PostgreSQL users 表） ──

MOCK_USERS = {
    "admin": {"id": "00000000-0000-0000-0000-000000000001", "username": "admin", "password": "admin123", "role": "admin"},
    "auditor": {"id": "00000000-0000-0000-0000-000000000002", "username": "auditor", "password": "auditor123", "role": "auditor"},
    "developer": {"id": "00000000-0000-0000-0000-000000000003", "username": "developer", "password": "dev123", "role": "developer"},
}


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """用户登录，签发 JWT access_token + refresh_token。"""
    user = MOCK_USERS.get(req.username)
    if user is None or user["password"] != req.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user["id"], user["username"], user["role"])
    # refresh_token 使用相同结构但更长过期时间
    refresh_token = create_access_token(user["id"], user["username"], user["role"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=86400,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest):
    """使用 refresh_token 获取新的 access_token。"""
    try:
        payload = decode_token(req.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    access_token = create_access_token(payload["sub"], payload["username"], payload["role"])
    refresh_token = create_access_token(payload["sub"], payload["username"], payload["role"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=86400,
    )
