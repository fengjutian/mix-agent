"""API 集成测试 — Phase 2 认证 + 审批流。

测试覆盖：
- T2.4.1 POST /api/v1/auth/login — JWT 登录
- T2.4.2 POST /api/v1/auth/refresh — Token 刷新
- T2.4.3 JWT 中间件：无 Token → 401，developer 访问审批 → 403
- T2.4.4 GET /api/v1/approvals/pending — 待审批列表
- T2.4.5 POST /api/v1/approvals/respond — 审批决策
"""

import pytest


def _login(client, username: str, password: str) -> str:
    """Helper: 登录并返回 access_token。"""
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


class TestAuthAPI:
    """T2.4.1-3 认证 API 测试。"""

    def test_login_success(self, client):
        """有效凭据登录返回 200 + access_token。"""
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client):
        """错误凭据返回 401。"""
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrong",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        """不存在的用户返回 401。"""
        resp = client.post("/api/v1/auth/login", json={
            "username": "nonexistent",
            "password": "xxx",
        })
        assert resp.status_code == 401

    def test_refresh_token(self, client):
        """使用 refresh_token 获取新 access_token。"""
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123",
        })
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_refresh_invalid_token(self, client):
        """无效 refresh_token 返回 401。"""
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
        assert resp.status_code == 401


class TestRoleAccess:
    """T2.4.3 角色访问控制测试。"""

    def test_no_token_returns_401_on_approvals(self, client):
        """无 Token 访问审批接口 → 401。"""
        resp = client.get("/api/v1/approvals/pending")
        assert resp.status_code == 401

    def test_developer_cannot_access_approvals(self, client):
        """developer 角色访问审批接口 → 403。"""
        token = _login(client, "developer", "dev123")
        resp = client.get("/api/v1/approvals/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_auditor_can_access_approvals(self, client):
        """auditor 角色访问审批接口 → 200。"""
        token = _login(client, "auditor", "auditor123")
        resp = client.get("/api/v1/approvals/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_admin_can_access_approvals(self, client):
        """admin 角色访问审批接口 → 200。"""
        token = _login(client, "admin", "admin123")
        resp = client.get("/api/v1/approvals/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestApprovalFlow:
    """T2.4.4-5 审批流完整测试。"""

    def test_pending_list_empty(self, client):
        """初始待审批列表为空。"""
        token = _login(client, "auditor", "auditor123")
        resp = client.get("/api/v1/approvals/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_approval_flow(self, client):
        """完整审批流程：注册审批 → 查看列表 → 审批通过。"""
        token = _login(client, "auditor", "auditor123")

        # 先注册一个待审批项（模拟 Agent 节点触发）
        from mix_agent.api.v1_approvals import register_pending_approval
        from mix_agent.schemas import ApprovalRequest

        ar = ApprovalRequest(
            task_id="test-approval-task",
            node_name="sql_risk_explain",
            prompt="发现 DROP TABLE 操作",
            context={"danger_count": 1},
        )
        register_pending_approval("test-approval-task", ar)

        # 查看待审批列表
        resp = client.get("/api/v1/approvals/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

        # 查看详情
        resp = client.get("/api/v1/approvals/pending/test-approval-task", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["prompt"] == "发现 DROP TABLE 操作"

        # 提交审批决策
        resp = client.post("/api/v1/approvals/respond", json={
            "task_id": "test-approval-task",
            "decision": "approve",
            "feedback": "已确认安全",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approve"

        # 审批后待审批列表不再包含该项
        resp = client.get("/api/v1/approvals/pending", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        resp_data = resp.json()
        assert not any(item["task_id"] == "test-approval-task" for item in resp_data["items"])
