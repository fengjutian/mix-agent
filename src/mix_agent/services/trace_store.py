"""AI 调用链分析历史持久化 — 基于 SQLite 的轻量存储。

与 TokenLogService 不同，本服务自管理 SQLAlchemy 引擎，
不依赖外部 PostgreSQL，确保开箱即用。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select, func, delete
from sqlalchemy.orm import Session, sessionmaker

from mix_agent.models import AiTraceRecord, Base

# 默认 SQLite 文件路径（项目根目录下的 data/ 目录）
_DEFAULT_DB_PATH: Path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "trace_history.db"


class TraceStore:
    """AI 分析历史 SQLite 存储。

    Usage:
        store = TraceStore()
        store.save(record_id="...", method="POST", url="...", result={...})
        records = store.list_all()
        store.delete("record_id")
    """

    def __init__(self, db_path: str | Path | None = None):
        path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        # 自动建表
        Base.metadata.create_all(self._engine, tables=[AiTraceRecord.__table__])
        self._session_factory = sessionmaker(bind=self._engine)

    # ── CRUD ──

    def save(
        self,
        record_id: str,
        method: str,
        url: str,
        result: dict,
        source_root: str | None = None,
    ) -> AiTraceRecord:
        """保存一条分析记录（若 ID 已存在则更新）。"""
        with self._session_factory() as session:
            existing = session.get(AiTraceRecord, record_id)
            if existing:
                existing.result = result
                existing.updated_at = datetime.now(timezone.utc)  # noqa
            else:
                record = AiTraceRecord(
                    id=record_id,
                    method=method,
                    url=url,
                    source_root=source_root,
                    result=result,
                )
                session.add(record)
            session.commit()
            return existing or record

    def get(self, record_id: str) -> dict | None:
        """获取单条记录。"""
        with self._session_factory() as session:
            record = session.get(AiTraceRecord, record_id)
            if record is None:
                return None
            return _record_to_dict(record)

    def list_all(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """列出所有记录，按创建时间倒序。"""
        with self._session_factory() as session:
            stmt = (
                select(AiTraceRecord)
                .order_by(AiTraceRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            records = session.execute(stmt).scalars().all()
            return [_record_to_dict(r) for r in records]

    def count(self) -> int:
        """记录总数。"""
        with self._session_factory() as session:
            return session.execute(
                select(func.count(AiTraceRecord.id))
            ).scalar_one()

    def delete(self, record_id: str) -> bool:
        """删除单条记录。返回是否成功删除。"""
        with self._session_factory() as session:
            result = session.execute(
                delete(AiTraceRecord).where(AiTraceRecord.id == record_id)
            )
            session.commit()
            return result.rowcount > 0

    def delete_all(self) -> int:
        """清空所有记录。返回删除数量。"""
        with self._session_factory() as session:
            count = session.execute(
                select(func.count(AiTraceRecord.id))
            ).scalar_one()
            session.execute(delete(AiTraceRecord))
            session.commit()
            return count


def _record_to_dict(r: AiTraceRecord) -> dict:
    return {
        "id": r.id,
        "method": r.method,
        "url": r.url,
        "source_root": r.source_root,
        "result": r.result,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# 模块级单例
trace_store = TraceStore()
