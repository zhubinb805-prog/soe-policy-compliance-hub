"""
向量存储服务 — 支持 ChromaDB / PGVector 双后端

职责:
  1. 文档块向量化 (Embedding)
  2. 向量存储 & 检索
  3. 按 doc_id 删除（支持增量更新）
"""

from __future__ import annotations

from typing import Any

from langchain_openai import OpenAIEmbeddings

from agents.doc_parser_agent import DocumentChunk
from config import settings


class DashScopeEmbeddings:
    """兼容阿里云 DashScope 的嵌入模型"""
    
    def __init__(self, api_key: str, model: str = "text-embedding-v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量"""
        import httpx
        results = []
        for text in texts:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": text[:8191]  # DashScope 限制
                    },
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                results.append(data["data"][0]["embedding"])
        return results
    
    async def aembed_query(self, text: str) -> list[float]:
        """生成单个查询向量"""
        return (await self.aembed_documents([text]))[0]


class VectorStoreService:
    """向量库统一接口，底层可切换 ChromaDB / PGVector"""

    COLLECTION_NAME = "knowledge_chunks"

    def __init__(self) -> None:
        # 根据 base_url 判断是否使用 DashScope
        if "dashscope" in settings.openai_base_url.lower():
            self.embeddings = DashScopeEmbeddings(
                api_key=settings.openai_api_key,
                model=settings.embedding_model,
            )
        else:
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        self._store: Any = None
        self._backend = settings.vector_store_type

    # ── initialization ───────────────────────────────────────

    async def init(self) -> None:
        if self._backend == "chroma":
            await self._init_chroma()
        else:
            await self._init_pgvector()

    async def _init_chroma(self) -> None:
        import chromadb
        client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        self._store = client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    async def _init_pgvector(self) -> None:
        from langchain_community.vectorstores import PGVector
        self._store = PGVector(
            connection_string=settings.pgvector_dsn,
            collection_name=self.COLLECTION_NAME,
            embedding_function=self.embeddings,
        )

    # ── CRUD ─────────────────────────────────────────────────

    async def add_chunks(self, chunks: list[DocumentChunk]) -> int:
        """向量化并存储文档块"""
        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        ids = [c.chunk_id for c in chunks]
        metadatas = [
            {
                "doc_id": c.doc_id,
                "doc_type": c.doc_type.value,
                "source": c.metadata.get("source", ""),
                "domain": c.metadata.get("domain", "soe_compliance"),
                "page": c.metadata.get("page", ""),
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]

        if self._backend == "chroma":
            vectors = await self.embeddings.aembed_documents(texts)
            self._store.upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=metadatas)
        else:
            await self._store.aadd_texts(texts=texts, metadatas=metadatas, ids=ids)

        return len(chunks)

    async def search(self, query: str, top_k: int = 5) -> list[tuple[dict, float]]:
        """语义搜索，返回 (文档, 分数) 列表"""
        if self._backend == "chroma":
            q_vec = await self.embeddings.aembed_query(query)
            results = self._store.query(query_embeddings=[q_vec], n_results=top_k, include=["documents", "metadatas", "distances"])
            out: list[tuple[dict, float]] = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                score = 1.0 - dist  # cosine distance → similarity
                out.append(({"content": doc, "source": meta.get("source", ""), "metadata": meta}, score))
            return out
        else:
            results = await self._store.asimilarity_search_with_score(query, k=top_k)
            return [
                ({"content": doc.page_content, "source": doc.metadata.get("source", ""), "metadata": doc.metadata}, score)
                for doc, score in results
            ]

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """按 doc_id 删除所有相关向量"""
        if self._backend == "chroma":
            existing = self._store.get(where={"doc_id": doc_id}, include=[])
            ids = existing.get("ids", [])
            if ids:
                self._store.delete(ids=ids)
            return len(ids)
        return 0

    async def get_stats(self) -> dict:
        """获取向量库统计信息"""
        if self._backend == "chroma":
            count = self._store.count()
            return {"backend": "chroma", "total_vectors": count, "collection": self.COLLECTION_NAME}
        return {"backend": "pgvector", "collection": self.COLLECTION_NAME}
