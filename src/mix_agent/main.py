"""FastAPI 应用启动入口、Uvicorn 服务配置、全局跨域中间件。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mix_agent.api.v1_admin import router as admin_router
from mix_agent.api.v1_agent import router as agent_router
from mix_agent.api.v1_tasks import router as tasks_router
from mix_agent.api.v1_analyzer import router as analyzer_router
from mix_agent.api.v1_review import router as review_router
from mix_agent.api.v1_pr import router as pr_router
from mix_agent.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化资源（Redis、Qdrant 连接池等）
    yield
    # 关闭时清理资源


app = FastAPI(
    title="mix-agent API",
    description="企业级多智能体协同系统 — A2A 协议交互接口",
    version="0.1.0",
    lifespan=lifespan,
)

# 全局跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(tasks_router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(analyzer_router, prefix="/api/v1/analyzer", tags=["analyzer"])
app.include_router(review_router, prefix="/api/v1/review", tags=["review"])
app.include_router(pr_router, prefix="/api/v1", tags=["pr"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
