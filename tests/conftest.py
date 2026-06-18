"""Pytest 公共夹具 — 提供 FastAPI TestClient、测试数据库、Mock 依赖等。"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mix_agent.main import app
from mix_agent.models import Base


# ──────────── 测试数据库（SQLite 内存数据库） ────────────

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    """创建同步 SQLite 内存引擎。"""
    eng = create_engine(TEST_DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """提供同步 SQLAlchemy Session。"""
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# ──────────── FastAPI TestClient ────────────


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """FastAPI 同步 TestClient。"""
    with TestClient(app) as c:
        yield c


# ──────────── 通用工具函数 ────────────


@pytest.fixture
def sample_task_id() -> str:
    """返回一个固定的测试用 task_id。"""
    return str(uuid.uuid4())


@pytest.fixture
def sample_task_payload() -> dict:
    """返回创建任务的标准请求体。"""
    return {
        "description": "检查用户模块的 SQL 安全性",
        "context": {
            "target_branch": "HEAD",
            "base_branch": "main",
            "repo_path": ".",
        },
    }
