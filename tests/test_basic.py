"""基础验证测试 — 确保项目骨架和测试框架可用。"""

import pytest


class TestHealthEndpoint:
    """验证 FastAPI 骨架正确启动。"""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_api_docs_accessible(self, client):
        """OpenAPI 文档可访问。"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "mix-agent API"


class TestDatabaseFixture:
    """验证数据库测试夹具。"""

    def test_engine_creates_tables(self, engine):
        """验证 SQLite 内存引擎可以创建所有表。"""
        from sqlalchemy import inspect

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        # Phase 1 核心表
        assert "users" in tables
        assert "teams" in tables
        assert "tasks" in tables
        assert "diff_files" in tables
        assert "audit_findings" in tables
        assert "audit_operation_log" in tables

    def test_session_can_insert(self, db_session):
        """验证 Session 可以写入数据。"""
        from mix_agent.models import Team, User

        team = Team(name="test_team")
        db_session.add(team)
        db_session.flush()

        user = User(username="test_user", password_hash="hash", role="developer", team_id=team.id)
        db_session.add(user)
        db_session.commit()

        assert db_session.query(User).count() == 1
        assert db_session.query(Team).count() == 1
