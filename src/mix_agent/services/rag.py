"""RAG 检索服务 — 嵌入向量化 + Qdrant 语义搜索 + 上下文注入。"""

from __future__ import annotations

import asyncio
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, Filter

from mix_agent.config import settings


class RAGService:
    """RAG 检索服务。

    职责：
    - 调用 LLM embedding API 将文本向量化
    - 存入 Qdrant 并支持语义检索
    - 将检索到的上下文注入 LLM Prompt
    """

    DEFAULT_EMBEDDING_SIZE = 1536  # text-embedding-3-small / MiniMax embedding
    COLLECTION_NAME = "audit_knowledge"

    def __init__(self, qdrant: QdrantClient):
        self._qdrant = qdrant
        self._ensure_collection()

    # ── 存储 ──

    async def ingest(self, texts: list[str], metadata_list: list[dict] | None = None) -> None:
        """将文本批次向量化并存入 Qdrant。

        Args:
            texts: 待入库的文本列表
            metadata_list: 对应的元数据列表（与 texts 等长）
        """
        if metadata_list is None:
            metadata_list = [{}] * len(texts)

        vectors = await self._embed(texts)
        points: list[PointStruct] = []

        for i, (text, meta) in enumerate(zip(texts, metadata_list)):
            import uuid
            point_id = str(uuid.uuid4())
            payload = {"text": text, **meta}
            points.append(
                PointStruct(id=point_id, vector=vectors[i], payload=payload)
            )

        self._qdrant.upsert(collection_name=self.COLLECTION_NAME, points=points)

    # ── 检索 ──

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """语义检索最相似的 top_k 条记录。"""
        query_vector = (await self._embed([query]))[0]
        hits = self._qdrant.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
        )
        return [
            {"score": hit.score, "text": hit.payload.get("text", ""), **hit.payload}
            for hit in hits
        ]

    async def search_with_context(
        self, query: str, max_tokens: int = 2000, top_k: int = 5
    ) -> str:
        """检索并拼接为上下文文本，可直接注入 Prompt。"""
        results = await self.search(query, top_k=top_k)
        if not results:
            return ""

        chunks: list[str] = []
        tokens_est = 0

        for r in results:
            text = r.get("text", "")
            # 粗估 token 数（中文 ~1.5 字符/token，英文 ~4 字符/token）
            est = len(text) // 3
            if tokens_est + est > max_tokens:
                break
            chunks.append(f"[score={r['score']:.3f}] {text}")
            tokens_est += est

        return "\n\n".join(chunks)

    # ── 场景化检索 ──

    async def find_similar_audits(self, description: str) -> str:
        """检索相似的历史审计结果。"""
        return await self.search_with_context(
            f"审计任务: {description}", max_tokens=1500, top_k=3
        )

    async def find_relevant_rules(self, code_context: str) -> str:
        """检索相关的安全规则/最佳实践。"""
        return await self.search_with_context(
            f"安全规则: {code_context}", max_tokens=1000, top_k=3
        )

    async def find_code_patterns(self, symbol_summary: str) -> str:
        """检索代码模式参考。"""
        return await self.search_with_context(
            f"代码模式: {symbol_summary}", max_tokens=1000, top_k=3
        )

    # ── 内部实现 ──

    def _ensure_collection(self) -> None:
        """确保集合存在。"""
        collections = self._qdrant.get_collections().collections
        if not any(c.name == self.COLLECTION_NAME for c in collections):
            self._qdrant.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.DEFAULT_EMBEDDING_SIZE,
                    distance=Distance.COSINE,
                ),
            )

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """调用 LLM embedding API 生成向量。

        优先使用 MiniMax embedding，否则降级为规则化 Hash 向量（测试用）。
        """
        # 尝试调用 MiniMax embedding API
        if settings.MINIMAX_API_KEY:
            try:
                return await self._embed_via_api(texts)
            except Exception:
                pass

        # 降级：确定性 Hash 向量（仅用于测试/开发）
        return [self._hash_embed(t) for t in texts]

    async def _embed_via_api(self, texts: list[str]) -> list[list[float]]:
        """通过 MiniMax embedding API 批量获取向量。"""
        import httpx

        url = f"{settings.MINIMAX_BASE_URL}/embeddings"
        headers = {"Authorization": f"Bearer {settings.MINIMAX_API_KEY}"}

        async with httpx.AsyncClient(timeout=60) as client:
            tasks = []
            for text in texts:
                tasks.append(
                    client.post(
                        url,
                        json={"model": "embo-01", "input": text},
                        headers=headers,
                    )
                )
            responses = await asyncio.gather(*tasks, return_exceptions=True)

        vectors: list[list[float]] = []
        for resp in responses:
            if isinstance(resp, Exception):
                raise RuntimeError(f"Embedding API call failed: {resp}")
            resp.raise_for_status()
            data = resp.json()
            vectors.append(data["data"][0]["embedding"])
        return vectors

    @staticmethod
    def _hash_embed(text: str) -> list[float]:
        """确定性 Hash 向量（测试降级方案）。"""
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        # 扩展到 target dims
        dims = RAGService.DEFAULT_EMBEDDING_SIZE
        vec: list[float] = []
        for i in range(dims):
            b = h[i % len(h)]
            vec.append((b / 255.0) * 2 - 1)  # normalize to [-1, 1]
        return vec
