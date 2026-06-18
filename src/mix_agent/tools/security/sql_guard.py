"""基于 SQLGlot 的高危 SQL 语法树静态审计门禁 — 判定 DDL/无条件 DML 的拦截器。"""

from dataclasses import dataclass, field
from enum import Enum

import sqlglot
from sqlglot import exp


class RiskLevel(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"


@dataclass
class AuditResult:
    """SQL 审计结果。"""
    sql: str
    risk_level: RiskLevel = RiskLevel.SAFE
    reasons: list[str] = field(default_factory=list)
    is_blocked: bool = False


class SQLGuard:
    """SQL 静态审计门禁。

    基于 SQLGlot 解析 SQL 语法树，识别并拦截高危操作：
    - DDL 语句：DROP、TRUNCATE、ALTER
    - 无 WHERE 条件的 UPDATE / DELETE
    - 其他可自定义规则
    """

    def __init__(self, block_ddl: bool = True, block_unconditional_dml: bool = True):
        self.block_ddl = block_ddl
        self.block_unconditional_dml = block_unconditional_dml

    def audit(self, sql: str) -> AuditResult:
        """对单条 SQL 执行静态审计，返回风险评估结果。"""
        result = AuditResult(sql=sql)

        try:
            parsed = sqlglot.parse_one(sql)
        except Exception as e:
            result.risk_level = RiskLevel.DANGER
            result.reasons.append(f"SQL 解析失败: {e}")
            result.is_blocked = True
            return result

        # ── DDL 检测 ──
        if isinstance(parsed, (exp.Drop, exp.Truncate, exp.Alter)):
            result.risk_level = RiskLevel.DANGER
            result.reasons.append(f"高危 DDL 操作被拦截: {parsed.sql()}")
            result.is_blocked = self.block_ddl

        # ── 无条件 DML 检测 ──
        if isinstance(parsed, (exp.Update, exp.Delete)):
            where = parsed.args.get("where")
            if where is None:
                result.risk_level = RiskLevel.DANGER
                result.reasons.append("无 WHERE 条件的 DML 操作被拦截")
                result.is_blocked = self.block_unconditional_dml

        return result

    def audit_batch(self, sqls: list[str]) -> list[AuditResult]:
        """批量审计多条 SQL。"""
        return [self.audit(s) for s in sqls]
