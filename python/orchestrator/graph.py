"""
LangGraph 编排引擎 — 4 Agent 混合编排 + 记忆系统 + MongoDB Checkpoint

编排模式:
  1. 文档入库流程: DocParser → KnowledgeExtract → (VectorStore + KnowledgeGraph)
  2. 问答流程: Query → QA Agent → (VectorRetrieval ∥ GraphRetrieval ∥ MemoryRetrieval) → Answer → MemoryStore
  3. 增量更新流程: CDC Event → UpdateAgent → (Diff → Parse → Store)

特性:
  - 每个节点执行完自动持久化状态到 MongoDB (LangGraph Checkpoint)
  - OOM 崩溃后用相同 thread_id 可从最近检查点恢复
  - 外部调用点幂等性保护 (request_id 去重)
  - 超时 + 指数退避重试机制
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from functools import wraps
from typing import Annotated, Any

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.doc_parser_agent import DocParserAgent, DocumentChunk
from agents.knowledge_extract_agent import ExtractionResult, KnowledgeExtractAgent
from agents.knowledge_update_agent import (
    ChangeType,
    DocumentChange,
    KnowledgeUpdateAgent,
    UpdateResult,
)
from agents.qa_agent import QAAgent, QAResult
from services.knowledge_graph import KnowledgeGraphService
from services.memory_service import MemoryService
from services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


# ── 幂等包装器 ─────────────────────────────────────────────

class IdempotentNode:
    """
    节点级幂等 + 超时重试装饰器。

    - 在 state 中维护 _executed_{node_name} 集合，
      已执行过的 request_id 直接跳过，避免重复副作用。
    - 超时后自动重试，指数退避，最多 max_retries 次。
    """

    def __init__(self, node_name: str, max_retries: int = 3, timeout_seconds: float = 60.0):
        self.node_name = node_name
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    def __call__(self, func):
        node_name = self.node_name
        max_retries = self.max_retries
        timeout_seconds = self.timeout_seconds

        @wraps(func)
        async def wrapper(state: dict) -> dict:
            request_id = state.get("request_id", "")
            executed_key = f"_executed_{node_name}"
            executed_set = state.get(executed_key, set()) or set()

            # 幂等检查: 该 request_id 已在此节点执行过则跳过
            if request_id and request_id in executed_set:
                logger.info(
                    "[Idempotent] 节点 %s 已执行过 request_id=%s，跳过",
                    node_name, request_id,
                )
                return {}

            # 带超时的重试执行
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    result = await asyncio.wait_for(
                        func(state), timeout=timeout_seconds,
                    )
                    # 标记该 request_id 已执行
                    new_executed = set(executed_set)
                    if request_id:
                        new_executed.add(request_id)
                    result[executed_key] = new_executed
                    return result
                except asyncio.TimeoutError:
                    last_error = (
                        f"节点 {node_name} 第 {attempt} 次执行超时 ({timeout_seconds}s)"
                    )
                    logger.warning(last_error)
                except Exception as e:
                    last_error = f"节点 {node_name} 第 {attempt} 次执行失败: {e}"
                    logger.warning(last_error)

                if attempt < max_retries:
                    backoff = min(2 ** attempt, 10)
                    logger.info("[Retry] %ds 后重试...", backoff)
                    await asyncio.sleep(backoff)

            raise RuntimeError(
                f"节点 {node_name} 重试 {max_retries} 次后仍失败: {last_error}"
            )

        return wrapper


class WorkflowType(str, Enum):    # 定义工作流类型枚举
    INGEST = "ingest"    # 文档入库工作流 
    QA = "qa"            # 问答工作流
    UPDATE = "update"    # 增量更新工作流


# ── State Schemas ────────────────────────────────────────────

class IngestState(dict):
    """文档入库流程状态"""
    file_paths: list[str]
    chunks: list[DocumentChunk]
    extractions: list[ExtractionResult]
    vectors_stored: int
    entities_stored: int
    messages: Annotated[list, add_messages]
    # 幂等 & checkpoint
    request_id: str
    _executed_parse: set
    _executed_extract: set
    _executed_store_vectors: set
    _executed_store_graph: set


class QAState(dict):
    """问答流程状态"""
    question: str
    session_id: str | None
    user_id: str | None
    result: QAResult | None
    messages: Annotated[list, add_messages]
    # 幂等 & checkpoint
    request_id: str
    _executed_answer: set


class UpdateState(dict):
    """增量更新流程状态"""
    changes: list[DocumentChange]
    results: list[UpdateResult]
    messages: Annotated[list, add_messages]
    # 幂等 & checkpoint
    request_id: str
    _executed_process: set
    _executed_retry: set
    retry_count: int


# ── Workflow Builder ─────────────────────────────────────────

def build_knowledge_graph_workflow(
    vector_store: VectorStoreService | None = None,
    knowledge_graph: KnowledgeGraphService | None = None,
    memory_service: MemoryService | None = None,
    checkpointer=None,
) -> dict[str, Any]:
    """
    构建三条编排流水线，返回 {"ingest": graph, "qa": graph, "update": graph}

    Args:
        checkpointer: LangGraph checkpoint saver (如 MongoDBSaver)，
                      传入后每个节点执行完自动持久化状态。
    """
    doc_parser = DocParserAgent()    # 文档解析智能体
    extractor = KnowledgeExtractAgent()    # 知识提取智能体
    qa_agent = QAAgent(               # 问答智能体
        vector_store=vector_store,
        knowledge_graph=knowledge_graph,
        memory_service=memory_service
    )
    update_agent = KnowledgeUpdateAgent(  # 增量更新智能体
        doc_parser=doc_parser,
        knowledge_extractor=extractor,
        vector_store=vector_store,
        knowledge_graph=knowledge_graph,
    )

    return {
        "ingest": _build_ingest_graph(doc_parser, extractor, vector_store, knowledge_graph, checkpointer=checkpointer),
        "qa": _build_qa_graph(qa_agent, checkpointer=checkpointer),
        "update": _build_update_graph(update_agent, checkpointer=checkpointer),
    }


# ── Ingest Pipeline ─────────────────────────────────────────
"""文档入库流程"""
def _build_ingest_graph(
    doc_parser: DocParserAgent,
    extractor: KnowledgeExtractAgent,
    vector_store: VectorStoreService | None,
    knowledge_graph: KnowledgeGraphService | None,
    checkpointer=None,
) -> StateGraph:

    @IdempotentNode("parse", max_retries=3, timeout_seconds=120)
    async def parse_documents(state: dict) -> dict:      # 文档解析节点
        file_paths = state.get("file_paths", [])
        chunks = await doc_parser.parse_batch(file_paths)
        return {"chunks": chunks}

    @IdempotentNode("extract", max_retries=3, timeout_seconds=180)
    async def extract_knowledge(state: dict) -> dict:     # 知识提取节点
        chunks = state.get("chunks", [])
        extractions = await extractor.extract(chunks)
        return {"extractions": extractions}

    @IdempotentNode("store_vectors", max_retries=3, timeout_seconds=120)
    async def store_vectors(state: dict) -> dict:         # 向量存储节点
        chunks = state.get("chunks", [])
        count = 0
        if vector_store and chunks:
            count = await vector_store.add_chunks(chunks)
        return {"vectors_stored": count}

    @IdempotentNode("store_graph", max_retries=3, timeout_seconds=120)
    async def store_graph(state: dict) -> dict:           # 知识图存储节点
        extractions = state.get("extractions", [])
        chunks = state.get("chunks", [])
        sources = {chunk.chunk_id: chunk.metadata.get("source", "") for chunk in chunks}
        entity_count = 0
        if knowledge_graph:
            for ext in extractions:
                for ent in ext.entities:
                    source = sources.get(ext.source_chunk_id, "")
                    await knowledge_graph.upsert_entity(ent, source=source)    # 插入或更新实体
                    entity_count += 1
                for rel in ext.relations:
                    await knowledge_graph.add_relation(rel, source=source)     # 添加关系
        return {"entities_stored": entity_count}

    graph = StateGraph(IngestState)
    graph.add_node("parse", parse_documents)     # 文档解析节点
    graph.add_node("extract", extract_knowledge)     # 知识提取节点
    graph.add_node("store_vectors", store_vectors)     # 向量存储节点
    graph.add_node("store_graph", store_graph)     # 知识图存储节点

    graph.set_entry_point("parse")     # 文档解析节点作为入口
    graph.add_edge("parse", "extract")     # 文档解析节点到知识提取节点的边
    graph.add_edge("extract", "store_vectors")     # 知识提取节点到向量存储节点的边
    graph.add_edge("store_vectors", "store_graph")    # 向量存储节点到知识图存储节点的边
    graph.add_edge("store_graph", END)     # 知识图存储节点到结束节点的边

    return graph.compile(checkpointer=checkpointer)


# ── QA Pipeline ──────────────────────────────────────────────
"""问答流程"""
def _build_qa_graph(qa_agent: QAAgent, checkpointer=None) -> StateGraph:

    @IdempotentNode("answer", max_retries=2, timeout_seconds=60)
    async def process_question(state: dict) -> dict:
        question = state.get("question", "")
        session_id = state.get("session_id")
        user_id = state.get("user_id")

        if session_id or user_id:
            qa_agent.set_session_context(session_id=session_id, user_id=user_id)    # 设置会话上下文

        result = await qa_agent.answer(question)    # 问答节点，调用qa_agent.answer方法
        return {"result": result}

    graph = StateGraph(QAState)    # 问答状态节点
    graph.add_node("answer", process_question)    # 问答节点, 处理用户问题
    graph.set_entry_point("answer")    # 问答节点作为入口, 处理用户问题
    graph.add_edge("answer", END)    # 问答节点到结束节点的边

    return graph.compile(checkpointer=checkpointer)    # 编译问答流程图


# ── Update Pipeline ──────────────────────────────────────────
"""增量更新流程"""
MAX_UPDATE_RETRIES = 3    # 最大重试次数，防止死循环

def _build_update_graph(update_agent: KnowledgeUpdateAgent, checkpointer=None) -> StateGraph:

    @IdempotentNode("process", max_retries=3, timeout_seconds=120)
    async def process_updates(state: dict) -> dict:    # 增量更新节点
        """处理增量更新"""
        changes = state.get("changes", [])
        results = await update_agent.process_batch(changes)
        return {"results": results}

    def should_continue(state: dict) -> str:    # 增量更新状态判断节点
        """判断是否继续重试失败的更新（最多重试 MAX_UPDATE_RETRIES 次）"""
        results = state.get("results", [])
        retry_count = state.get("retry_count", 0)
        failed = [r for r in results if not r.success]
        if failed and retry_count < MAX_UPDATE_RETRIES:
            return "retry"
        return "done"

    @IdempotentNode("retry", max_retries=1, timeout_seconds=120)
    async def retry_failed(state: dict) -> dict:    # 增量更新重试节点
        """重试失败的更新，递增 retry_count"""
        retry_count = state.get("retry_count", 0) + 1
        results = state.get("results", [])
        failed_changes = [r.change for r in results if not r.success]
        retried = await update_agent.process_batch(failed_changes)
        all_results = [r for r in results if r.success] + retried
        return {"results": all_results, "retry_count": retry_count}

    graph = StateGraph(UpdateState)
    graph.add_node("process", process_updates)
    graph.add_node("retry", retry_failed)

    graph.set_entry_point("process")
    graph.add_conditional_edges("process", should_continue, {"retry": "retry", "done": END})
    graph.add_edge("retry", END)

    return graph.compile(checkpointer=checkpointer)
