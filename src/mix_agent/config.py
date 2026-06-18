"""全局配置中心 — 基于 Pydantic Settings 统一管理异构模型选型及安全阈值。"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ---------- 数据库 ----------
    DATABASE_URL: str = "postgresql+asyncpg://mixagent:mixagent_dev@localhost:5432/mixagent"

    # ---------- LLM 模型配置 ----------
    # MiniMax (OpenAI 兼容接口)
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimax.chat/v1"
    MINIMAX_MODEL: str = "MiniMax-Text-01"

    # DeepSeek (OpenAI 兼容接口)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---------- 向量数据库 ----------
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "code_summary"

    # ---------- Redis ----------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------- Docker 沙箱 ----------
    SANDBOX_IMAGE: str = "python:3.11-slim"
    SANDBOX_CPU_LIMIT: float = 2.0
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_TIMEOUT: int = 30

    # ---------- 安全门禁 ----------
    SQLGUARD_ENABLED: bool = True
    SQLGUARD_BLOCK_DDL: bool = True
    SQLGUARD_BLOCK_UNCONDITIONAL_DML: bool = True

    # ---------- CORS ----------
    CORS_ORIGINS: list[str] = ["*"]

    # ---------- Token 限流 ----------
    TOKEN_BURST_LIMIT: int = 100_000
    TOKEN_REFILL_RATE: int = 10_000

    # ---------- JWT ----------
    JWT_SECRET: str = "mix-agent-dev-secret-change-in-production"
    JWT_EXPIRE_SECONDS: int = 86400  # 24 hours

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
