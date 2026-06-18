"""API 集成测试 — Phase 1 确定性扫描端到端验证。"""

import json


class TestTaskAPI:
    """T1.3.1-5 任务 API 集成测试。"""

    def test_create_task_returns_201(self, client):
        """POST /api/v1/tasks/ — 创建任务返回 201。"""
        response = client.post("/api/v1/tasks/", json={
            "description": "test scan",
            "target_branch": "HEAD",
            "base_branch": "HEAD~1",
            "repo_path": ".",
        })
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] in ("completed", "running", "failed")

    def test_get_task_returns_detail(self, client):
        """GET /api/v1/tasks/{id} — 查询任务返回详情。"""
        # 先创建任务
        create_resp = client.post("/api/v1/tasks/", json={
            "description": "test",
            "target_branch": "HEAD",
            "base_branch": "HEAD~1",
            "repo_path": ".",
        })
        task_id = create_resp.json()["task_id"]

        # 查询
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("completed", "running", "failed")

    def test_get_findings(self, client):
        """GET /api/v1/tasks/{id}/findings — 查询发现项。"""
        create_resp = client.post("/api/v1/tasks/", json={
            "description": "test",
            "target_branch": "HEAD",
            "base_branch": "HEAD~1",
            "repo_path": ".",
        })
        task_id = create_resp.json()["task_id"]

        response = client.get(f"/api/v1/tasks/{task_id}/findings")
        assert response.status_code == 200
        data = response.json()
        assert "findings" in data
        assert isinstance(data["findings"], list)
        assert "total" in data

    def test_get_report(self, client):
        """GET /api/v1/tasks/{id}/report — 获取审计报告。"""
        create_resp = client.post("/api/v1/tasks/", json={
            "description": "test",
            "target_branch": "HEAD",
            "base_branch": "HEAD~1",
            "repo_path": ".",
        })
        task_id = create_resp.json()["task_id"]

        # JSON 格式
        response = client.get(f"/api/v1/tasks/{task_id}/report?format=json")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert "total_findings" in data
        assert "changed_files" in data

        # Markdown 格式 (format=md 也会被接受)
        response_md = client.get(f"/api/v1/tasks/{task_id}/report?format=md")
        assert response_md.status_code == 200

    def test_cancel_task(self, client):
        """POST /api/v1/tasks/{id}/cancel — 取消任务。"""
        create_resp = client.post("/api/v1/tasks/", json={
            "description": "test",
            "target_branch": "HEAD",
            "base_branch": "HEAD~1",
            "repo_path": ".",
        })
        task_id = create_resp.json()["task_id"]

        response = client.post(f"/api/v1/tasks/{task_id}/cancel")
        # 任务可能已经完成，但端点应正常返回
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id

    def test_task_not_found_returns_404(self, client):
        """不存在的任务返回 404。"""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404

        response = client.get(f"/api/v1/tasks/{fake_id}/findings")
        assert response.status_code == 404

        response = client.get(f"/api/v1/tasks/{fake_id}/report")
        assert response.status_code == 404

        response = client.post(f"/api/v1/tasks/{fake_id}/cancel")
        assert response.status_code == 404

    def test_e2e_flow(self, client):
        """端到端流程：创建 → 查询状态 → 查询发现项 → 获取报告。"""
        # 1. 创建任务
        create_resp = client.post("/api/v1/tasks/", json={
            "description": "e2e test",
            "target_branch": "HEAD",
            "base_branch": "HEAD~1",
            "repo_path": ".",
        })
        assert create_resp.status_code == 201
        task_id = create_resp.json()["task_id"]

        # 2. 查询状态
        status_resp = client.get(f"/api/v1/tasks/{task_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] in ("completed", "running", "failed")

        # 3. 查询发现项
        findings_resp = client.get(f"/api/v1/tasks/{task_id}/findings")
        assert findings_resp.status_code == 200
        findings = findings_resp.json()["findings"]
        # 应该至少有 git_diff 发现项
        assert any(f["agent"] == "git_diff" for f in findings), \
            "Should have git_diff findings for changed files"

        # 4. 获取报告
        report_resp = client.get(f"/api/v1/tasks/{task_id}/report")
        assert report_resp.status_code == 200
        report = report_resp.json()
        assert report["total_findings"] == len(findings)


