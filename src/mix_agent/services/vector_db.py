"""Qdrant 向量数据库服务 — 支持代码逆向业务摘要检索、混合过滤与按需局部召回。"""

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
)


class VectorDBService:
    """Qdrant 向量数据库服务。

    职责：
    - 代码业务摘要的向量化存储与检索
    - 混合过滤（关键词 + 语义向量）
    - 按需局部召回
    """

    def __init__(self, client: QdrantClient, collection: str = "code_summary"):
        self._client = client
        self._collection = collection

    def ensure_collection(self, vector_size: int = 768) -> None:
        """确保集合存在，不存在则创建。"""
        collections = self._client.get_collections().collections
        if not any(c.name == self._collection for c in collections):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, points: list[PointStruct]) -> None:
        """写入/更新向量点。"""
        self._client.upsert(collection_name=self._collection, points=points)

    def search(self, vector: list[float], top_k: int = 5, query_filter: Any | None = None) -> list[Any]:
        """语义检索最相似的 top_k 条记录。"""
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
        )
        return hits

    def delete(self, point_ids: list[str]) -> None:
        """按 ID 删除向量点。"""
        self._client.delete(
            collection_name=self._collection,
            points_selector=point_ids,
        )
