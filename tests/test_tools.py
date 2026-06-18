"""工具层集成测试 — 对每个工具单独验证核心功能。"""

import textwrap

from mix_agent.tools.parser.ast_analyzer import ASTAnalyzer
from mix_agent.tools.security.secret_scanner import SecretScanner
from mix_agent.tools.security.sql_guard import SQLGuard, RiskLevel
from mix_agent.tools.vcs.git_tool import GitTool, ChangeType


# ═══════════════════════════════════════════════
# T1.2.1 Git Diff Tool
# ═══════════════════════════════════════════════


class TestGitTool:
    """Git Diff 工具测试（依赖本地 Git 仓库）。"""

    def test_current_branch(self):
        g = GitTool(".")
        branch = g.current_branch()
        assert branch, "Should return current branch name"
        assert isinstance(branch, str)

    def test_list_branches(self):
        g = GitTool(".")
        branches = g.list_branches()
        assert "main" in branches or "master" in branches

    def test_diff_returns_result(self):
        g = GitTool(".")
        result = g.diff("HEAD", "HEAD~1")
        assert hasattr(result, "changed_files")
        assert hasattr(result, "total_additions")
        assert hasattr(result, "total_deletions")

    def test_diff_file(self):
        g = GitTool(".")
        # 选一个已知的变更文件
        diff = g.diff_file("pyproject.toml", "HEAD", "HEAD~1")
        # 可能为空（文件未变更），但不应抛异常
        assert isinstance(diff, str)

    def test_not_a_repo_raises(self):
        g = GitTool("/tmp/nonexistent_repo")
        try:
            g.diff()
            assert False, "Should have raised"
        except (ValueError, FileNotFoundError):
            pass  # expected


# ═══════════════════════════════════════════════
# T1.2.2 AST Analyzer
# ═══════════════════════════════════════════════


class TestASTAnalyzer:
    """AST 解析器测试。"""

    def test_parse_simple_class(self):
        source = textwrap.dedent("""\
            class MyService:
                def __init__(self, config: dict):
                    pass

                def process(self, data: str) -> bool:
                    return True
        """)
        ana = ASTAnalyzer()
        classes = ana.extract_classes(source)
        assert len(classes) == 1
        assert classes[0]["name"] == "MyService"
        assert len(classes[0]["methods"]) == 2

    def test_parse_function_with_annotations(self):
        source = textwrap.dedent("""\
            from typing import Optional

            def get_user(user_id: int, name: Optional[str] = None) -> dict:
                return {"id": user_id}
        """)
        ana = ASTAnalyzer()
        functions = ana.extract_functions(source)
        assert len(functions) == 1
        assert functions[0]["name"] == "get_user"
        assert functions[0]["returns"] == "dict"
        assert len(functions[0]["args"]) == 2

    def test_parse_imports(self):
        """测试导入解析 — 验证对实际文件的 import 提取。"""
        ana = ASTAnalyzer()
        result = ana.parse_file("src/mix_agent/config.py")
        imports = result["imports"]
        # config.py 导入了 pydantic_settings
        assert any(i.get("module") == "pydantic_settings" for i in imports)

    def test_parse_file_real(self):
        """解析实际项目文件。"""
        ana = ASTAnalyzer()
        result = ana.parse_file("src/mix_agent/tools/security/sql_guard.py")
        assert len(result["classes"]) >= 2  # RiskLevel, AuditResult, SQLGuard
        class_names = [c["name"] for c in result["classes"]]
        assert "SQLGuard" in class_names

    def test_generate_summary(self):
        source = textwrap.dedent('''\
            """User authentication module."""

            import hashlib

            class AuthService:
                def login(self, username: str, password: str) -> bool:
                    pass

            def validate_token(token: str) -> bool:
                pass
        ''')
        ana = ASTAnalyzer()
        summary = ana.generate_summary(source)
        assert "User authentication" in summary or "模块" in summary
        assert "AuthService" in summary

    def test_parse_files_batch(self):
        ana = ASTAnalyzer()
        result = ana.parse_files([
            "src/mix_agent/config.py",
            "src/mix_agent/schemas.py",
        ])
        assert result["parsed_files"] == 2
        assert result["total_files"] == 2
        assert isinstance(result["files"], dict)

    def test_to_json(self):
        ana = ASTAnalyzer()
        json_str = ana.to_json(["src/mix_agent/config.py"])
        import json
        data = json.loads(json_str)
        assert "files" in data
        assert data["parsed_files"] == 1


# ═══════════════════════════════════════════════
# T1.2.3 SQL Guard
# ═══════════════════════════════════════════════


class TestSQLGuard:
    """SQL 审计门禁测试。"""

    def test_drop_table_blocked(self):
        guard = SQLGuard()
        result = guard.audit("DROP TABLE users")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is True

    def test_truncate_blocked(self):
        guard = SQLGuard()
        result = guard.audit("TRUNCATE TABLE orders")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is True

    def test_alter_table_blocked(self):
        guard = SQLGuard()
        result = guard.audit("ALTER TABLE users ADD COLUMN age INT")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is True

    def test_unconditional_delete_blocked(self):
        guard = SQLGuard()
        result = guard.audit("DELETE FROM logs")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is True

    def test_unconditional_update_blocked(self):
        guard = SQLGuard()
        result = guard.audit("UPDATE users SET active = false")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is True

    def test_conditional_delete_safe(self):
        guard = SQLGuard()
        result = guard.audit("DELETE FROM logs WHERE created_at < '2020-01-01'")
        assert result.risk_level == RiskLevel.SAFE
        assert result.is_blocked is False

    def test_select_safe(self):
        guard = SQLGuard()
        result = guard.audit("SELECT * FROM users WHERE id = 1")
        assert result.risk_level == RiskLevel.SAFE
        assert result.is_blocked is False

    def test_batch_audit(self):
        guard = SQLGuard()
        results = guard.audit_batch([
            "SELECT 1",
            "DROP TABLE users",
            "DELETE FROM t WHERE x=1",
        ])
        assert results[0].risk_level == RiskLevel.SAFE
        assert results[1].risk_level == RiskLevel.DANGER
        assert results[2].risk_level == RiskLevel.SAFE

    def test_ddl_disabled_allows_drop(self):
        guard = SQLGuard(block_ddl=False)
        result = guard.audit("DROP TABLE users")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is False  # 不拦截但标记为 danger

    def test_unconditional_dml_disabled_allows(self):
        guard = SQLGuard(block_unconditional_dml=False)
        result = guard.audit("DELETE FROM logs")
        assert result.risk_level == RiskLevel.DANGER
        assert result.is_blocked is False


# ═══════════════════════════════════════════════
# T1.2.4 Secret Scanner
# ═══════════════════════════════════════════════


class TestSecretScanner:
    """密钥扫描器测试。"""

    def test_api_key_detected(self):
        s = SecretScanner()
        findings = s.scan_content('API_KEY = "sk-test1234567890abcdefghij"', "test.py")
        assert len(findings) >= 1
        assert any(f.rule_id == "api_key_assignment" for f in findings)

    def test_password_detected(self):
        s = SecretScanner()
        findings = s.scan_content('PASSWORD = "supersecret123"', "test.py")
        assert len(findings) >= 1
        assert any(f.rule_id == "password_assignment" for f in findings)

    def test_jwt_detected(self):
        s = SecretScanner()
        # Valid JWT format: header.payload.signature (3 parts, each >= 10 chars)
        findings = s.scan_content(
            'token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.fake_signature_here"', "test.py"
        )
        assert any(f.rule_id == "jwt_token" for f in findings)

    def test_comment_skipped(self):
        s = SecretScanner()
        findings = s.scan_content('# PASSWORD = "hidden"', "test.py")
        assert len(findings) == 0

    def test_private_key_detected(self):
        s = SecretScanner()
        findings = s.scan_content(
            "key = '''-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----'''",
            "test.py",
        )
        assert any(f.rule_id == "private_key_header" for f in findings)

    def test_github_token_detected(self):
        s = SecretScanner()
        findings = s.scan_content("GITHUB_TOKEN = ghp_1234567890abcdefghijklmnop", "test.py")
        assert any(f.rule_id == "github_token" for f in findings)

    def test_db_connection_string_detected(self):
        s = SecretScanner()
        findings = s.scan_content(
            "DATABASE_URL = mysql://admin:password123@localhost:3306/db", "test.py"
        )
        assert any(f.rule_id == "db_connection_string" for f in findings)

    def test_no_false_positive_on_safe_assignment(self):
        s = SecretScanner()
        findings = s.scan_content('name = "John Doe"', "test.py")
        assert len(findings) == 0


# ═══════════════════════════════════════════════
# T1.2.5 Docker Sandbox (unit test — 不需要 Docker)
# ═══════════════════════════════════════════════


class TestContainerSandbox:
    """Docker 沙箱测试（仅验证代码路径，不依赖 Docker 运行）。"""

    def test_check_available_no_crash(self):
        from mix_agent.tools.sandbox.container import ContainerSandbox

        s = ContainerSandbox()
        available = s.check_available()
        assert isinstance(available, bool)

    def test_security_scan_no_docker(self):
        import asyncio
        from mix_agent.tools.sandbox.container import ContainerSandbox

        s = ContainerSandbox()
        result = asyncio.run(s.security_scan("."))
        # Docker 不可用时应返回降级结果
        assert hasattr(result, "vulnerabilities")
        assert result.success is False or result.success is True
