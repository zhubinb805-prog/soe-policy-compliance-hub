"""
FastAPI 入口 — 央国企制度与合规知识库 REST API

提供三组接口:
  1. /api/ingest   — 文档上传 & 入库
  2. /api/qa       — 智能问答
  3. /api/admin    — 管理（统计、更新触发）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import os
import shutil
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.doc_parser_agent import DocParserAgent
from agents.knowledge_extract_agent import KnowledgeExtractAgent
from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
from config import settings
from orchestrator.graph import build_knowledge_graph_workflow
from services.knowledge_graph import KnowledgeGraphService
from services.memory_service import MemoryService
from services.vector_store import VectorStoreService
from services.compliance_rules import check_procurement

vector_store = VectorStoreService()
knowledge_graph = KnowledgeGraphService()
memory_service = MemoryService()
doc_parser = DocParserAgent()
extractor = KnowledgeExtractAgent()
workflows: dict[str, Any] = {}
mongo_client = None

# 初始化知识图谱和工作流
@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化知识图谱和工作流"""
    global mongo_client
    os.makedirs(settings.upload_dir, exist_ok=True)   # 确保上传目录存在
    try:
        await vector_store.init()    # 初始化向量存储
    except Exception:
        pass
    try:
        await knowledge_graph.init()    # 初始化知识图谱
    except Exception:
        pass

    # 初始化 MongoDB checkpointer
    from pymongo import MongoClient
    from langgraph.checkpoint.mongodb import MongoDBSaver
    mongo_client = MongoClient(settings.mongodb_uri)
    checkpointer = MongoDBSaver(
        client=mongo_client,
        db_name=settings.mongodb_database,
    )

    workflows.update(                   # 初始化知识图谱工作流
        build_knowledge_graph_workflow(
            vector_store=vector_store,
            knowledge_graph=knowledge_graph,
            memory_service=memory_service,
            checkpointer=checkpointer,
        )
    )
    yield
    await knowledge_graph.close()
    if mongo_client:
        mongo_client.close()


app = FastAPI(         # 初始化FastAPI应用
    title="央国企制度知识图谱与合规预审平台 API",
    description="面向央国企制度梳理、内控诊断与合规问答的多 Agent 知识服务",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(    # 添加CORS中间件，允许跨域请求
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────────

class QuestionRequest(BaseModel):  # 问答请求模型
    """问答请求模型"""
    question: str
    session_id: str | None = None
    user_id: str | None = None


class QuestionResponse(BaseModel):  # 问答响应模型
    """问答响应模型"""
    question: str
    answer: str
    confidence: float
    intent: str
    sources: list[dict[str, Any]]
    reasoning_steps: list[str]


class IngestResponse(BaseModel):  # 文档入库响应模型
    """文档入库响应模型"""
    file_name: str
    chunks_count: int
    entities_count: int
    relations_count: int
    status: str


class StatsResponse(BaseModel):  # 统计响应模型
    """统计响应模型"""
    vector_store: dict[str, Any]
    knowledge_graph: dict[str, Any]


class UpdateRequest(BaseModel):  # 更新请求模型
    """更新请求模型"""
    file_path: str
    change_type: str = "modified"


class UpdateResponse(BaseModel):  # 更新响应模型
    """更新响应模型"""
    file_path: str
    vectors_added: int
    vectors_deleted: int
    entities_added: int
    relations_added: int
    success: bool
    processing_time_ms: float


class ComplianceCheckRequest(BaseModel):
    amount: float
    scope: str = "集团总部及所属全资、控股子公司"


class ComplianceCheckResponse(BaseModel):
    scenario: str
    amount: float
    scope: str
    required_steps: list[str]
    risk_flags: list[str]
    basis: list[str]
    next_action: str


# ── Ingest Endpoints ─────────────────────────────────────────
# 文档入库接口
@app.post("/api/ingest/upload", response_model=IngestResponse, tags=["文档入库"])
async def upload_document(file: UploadFile = File(...)):
    """上传并解析文档，自动入库到向量库和知识图谱（通过 ingest workflow + checkpoint）"""
    import logging
    logger = logging.getLogger(__name__)

    original_name = file.filename or "unknown"
    safe_name = os.path.basename(original_name)
    allowed_extensions = set(DocParserAgent.SUPPORTED_EXTENSIONS)
    if safe_name != original_name or Path(safe_name).suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=400, detail="仅支持 PDF、DOCX、TXT、MD、CSV、XLSX 和图片文件")
    save_path = os.path.join(settings.upload_dir, safe_name)    # 上传文件保存路径
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)    # 复制文件内容到保存路径

    try:
        ingest_wf = workflows.get("ingest")
        if not ingest_wf:
            raise HTTPException(status_code=503, detail="Ingest workflow not initialized")

        thread_id = f"ingest-{safe_name}"
        request_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"开始入库文档: {save_path}, thread_id={thread_id}")
        result = await ingest_wf.ainvoke(
            {"file_paths": [save_path], "request_id": request_id},
            config=config,
        )

        chunks = result.get("chunks", [])
        extractions = result.get("extractions", [])
        total_entities = sum(len(e.entities) for e in extractions) if extractions else 0
        total_relations = sum(len(e.relations) for e in extractions) if extractions else 0

        return IngestResponse(
            file_name=safe_name,
            chunks_count=len(chunks),
            entities_count=total_entities,
            relations_count=total_relations,
            status="success",
        )
    except Exception as e:
        logger.error(f"上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.post("/api/ingest/batch", response_model=list[IngestResponse], tags=["文档入库"])
async def upload_batch(files: list[UploadFile] = File(...)):
    """批量上传文档"""
    results = []
    for file in files:
        resp = await upload_document(file)
        results.append(resp)
    return results


@app.get("/api/ingest/documents", tags=["文档入库"])
async def get_documents():
    """获取已上传文档列表"""
    documents = []
    if os.path.exists(settings.upload_dir):
        for filename in os.listdir(settings.upload_dir):
            filepath = os.path.join(settings.upload_dir, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                documents.append({
                    "id": filename,
                    "name": filename,
                    "size": stat.st_size,
                    "upload_time": stat.st_ctime,
                    "chunks_count": 0
                })
    return documents


@app.delete("/api/ingest/documents/{file_name}", tags=["文档入库"])
async def delete_document(file_name: str):
    """删除已上传的文档"""
    safe_name = os.path.basename(file_name)
    if safe_name != file_name:
        raise HTTPException(status_code=400, detail="Invalid document name")
    filepath = os.path.join(settings.upload_dir, safe_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        doc_id = doc_parser._make_doc_id(filepath)
        await vector_store.delete_by_doc_id(doc_id)
        await knowledge_graph.delete_by_source(filepath)
        os.remove(filepath)
        return {"success": True, "message": f"Document {safe_name} and its knowledge records were deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


# ── QA Endpoints ─────────────────────────────────────────────

@app.post("/api/qa/ask", response_model=QuestionResponse, tags=["智能问答"])
async def ask_question(req: QuestionRequest):
    """智能问答 — 混合检索 + 知识图谱推理 + 记忆系统"""
    qa_wf = workflows.get("qa")      ### 从工作流字典，获取智能问答工作流
    if not qa_wf:
        raise HTTPException(status_code=503, detail="QA workflow not initialized")

    thread_id = req.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {
        "question": req.question,
        "request_id": request_id,
    }     # 初始化输入参数，包含问题和幂等 ID
    if req.session_id:
        inputs["session_id"] = req.session_id    # 如果提供了会话 ID，添加到输入参数
    if req.user_id:
        inputs["user_id"] = req.user_id    # 如果提供了用户 ID，添加到输入参数

    result = await qa_wf.ainvoke(inputs, config=config)    # 调用智能问答工作流，带 thread_id 支持 checkpoint 恢复
    qa_result = result.get("result")     # 从工作流结果中提取问答结果
    if not qa_result:
        raise HTTPException(status_code=500, detail="QA failed")

    return QuestionResponse(        # 返回问答结果
        question=qa_result.question,     # 问答结果中的问题
        answer=qa_result.answer,       # 问答结果中的答案 
        confidence=qa_result.confidence,  # 问答结果中的置信度
        intent=qa_result.intent.value,    # 问答结果中的意图
        sources=[
            {
                "content": c.content[:300],
                "source": os.path.basename(c.source) if c.source != "knowledge_graph" else "知识图谱",
                "score": c.score,
                "type": c.retrieval_type,
                "page": c.metadata.get("page"),
            }
            for c in qa_result.contexts
        ],
        reasoning_steps=qa_result.reasoning_steps,
    )


# ── Compliance pre-check ────────────────────────────────────

@app.post("/api/compliance/procurement-check", response_model=ComplianceCheckResponse, tags=["合规预审"])
async def procurement_compliance_check(req: ComplianceCheckRequest):
    """基于可审计规则快速判断采购审批路径，并返回制度依据。"""
    try:
        result = check_procurement(req.amount, req.scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComplianceCheckResponse(
        scenario="采购审批预审",
        amount=result.amount,
        scope=result.scope,
        required_steps=result.required_steps,
        risk_flags=result.risk_flags,
        basis=result.basis,
        next_action=result.next_action,
    )


# ── Admin Endpoints ──────────────────────────────────────────

@app.get("/api/admin/stats", response_model=StatsResponse, tags=["系统管理"])
async def get_stats():
    """获取系统统计信息"""
    vs_stats = await vector_store.get_stats()
    kg_stats = await knowledge_graph.get_stats()
    return StatsResponse(vector_store=vs_stats, knowledge_graph=kg_stats)


@app.post("/api/admin/update", response_model=UpdateResponse, tags=["系统管理"])
async def trigger_update(req: UpdateRequest):
    """手动触发知识更新"""
    update_wf = workflows.get("update")     ### 从工作流字典，获取知识更新工作流
    if not update_wf:
        raise HTTPException(status_code=503, detail="Update workflow not initialized")

    thread_id = f"update-{req.file_path}"
    request_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    change = DocumentChange(
        file_path=req.file_path,
        change_type=ChangeType(req.change_type),
    )
    result = await update_wf.ainvoke(
        {"changes": [change], "request_id": request_id},
        config=config,
    )
    results = result.get("results", [])
    if not results:
        raise HTTPException(status_code=500, detail="Update failed")

    r = results[0]
    return UpdateResponse(
        file_path=r.change.file_path,
        vectors_added=r.vectors_added,
        vectors_deleted=r.vectors_deleted,
        entities_added=r.entities_added,
        relations_added=r.relations_added,
        success=r.success,
        processing_time_ms=r.processing_time_ms,
    )


# ── Memory Endpoints ─────────────────────────────────────────

class UserProfileRequest(BaseModel):  # 用户配置请求模型
    """用户配置请求模型"""
    user_id: str
    name: str | None = None
    background: str | None = None
    preferences: dict | None = None

class UserProfileResponse(BaseModel):  # 用户配置响应模型
    """用户配置响应模型"""
    user_id: str
    name: str
    background: str
    preferences: dict
    interaction_count: int
    last_active: str
    created_at: str

class PersonalityRequest(BaseModel):  # 人格配置请求模型
    """人格配置请求模型"""
    user_id: str
    warmth: float | None = None
    expertise: float | None = None
    humor: float | None = None
    empathy: float | None = None

class PersonalityResponse(BaseModel):  # 人格配置响应模型
    """人格配置响应模型"""
    user_id: str
    warmth: float
    expertise: float
    humor: float
    empathy: float

class MemoryRetrieveRequest(BaseModel):  # 记忆检索请求模型
    """记忆检索请求模型"""
    query: str
    user_id: str = "default_user"
    top_k: int = 5

class MemoryEventResponse(BaseModel):  # 记忆事件响应模型
    """记忆事件响应模型"""
    session_id: str
    timestamp: str
    user_input: str
    agent_response: str
    summary: str
    topics: list[str]
    importance: float

# ── Conversation Models ───────────────────────────────────────

class MessageRequest(BaseModel):  # 消息请求模型
    """消息请求模型"""
    role: str  # user | assistant | system
    content: str
    message_id: str | None = None
    metadata: dict | None = None

class MessageResponse(BaseModel):  # 消息响应模型
    """消息响应模型"""
    id: str
    session_id: str
    role: str
    content: str
    timestamp: str
    metadata: dict

class ConversationRequest(BaseModel):  # 对话请求模型
    """对话请求模型"""
    session_id: str
    user_id: str | None = None
    title: str | None = None
    metadata: dict | None = None

class ConversationResponse(BaseModel):  # 对话响应模型
    """对话响应模型"""
    session_id: str
    user_id: str
    title: str
    messages: list[MessageResponse]
    created_at: str
    updated_at: str
    metadata: dict

class ConversationListResponse(BaseModel):  # 对话列表响应模型
    """对话列表响应模型"""
    conversations: list[ConversationResponse]
    total: int

class ConversationSearchRequest(BaseModel):  # 对话搜索请求模型
    """对话搜索请求模型"""
    query: str
    user_id: str | None = None
    limit: int = 20

class DeleteMessageRequest(BaseModel):  # 删除消息请求模型
    """删除消息请求模型"""
    message_id: str

@app.get("/api/memory/profile/{user_id}", response_model=UserProfileResponse, tags=["记忆管理"])   # 获取用户画像接口
async def get_user_profile(user_id: str):
    """获取用户画像"""
    profile = await memory_service.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    return UserProfileResponse(
        user_id=profile.user_id,
        name=profile.name,
        background=profile.background,
        preferences=profile.preferences,
        interaction_count=profile.interaction_count,
        last_active=profile.last_active,
        created_at=profile.created_at,
    )

@app.post("/api/memory/profile", response_model=UserProfileResponse, tags=["记忆管理"])   # 更新用户画像接口
async def update_user_profile(req: UserProfileRequest):
    """更新用户画像"""
    profile = await memory_service.get_user_profile(req.user_id)
    if not profile:
        from services.memory_models import UserProfile
        profile = UserProfile(user_id=req.user_id)
    
    if req.name is not None:
        profile.name = req.name
    if req.background is not None:
        profile.background = req.background
    if req.preferences is not None:
        profile.preferences.update(req.preferences)
    
    await memory_service.update_user_profile(req.user_id, profile)   # 更新用户画像
    return UserProfileResponse(
        user_id=profile.user_id,
        name=profile.name,
        background=profile.background,
        preferences=profile.preferences,
        interaction_count=profile.interaction_count,
        last_active=profile.last_active,
        created_at=profile.created_at,
    )

@app.get("/api/memory/personality/{user_id}", response_model=PersonalityResponse, tags=["记忆管理"])   # 获取AI个性参数接口
async def get_personality(user_id: str):
    """获取AI个性参数"""
    personality = await memory_service.get_personality(user_id)
    return PersonalityResponse(
        user_id=user_id,
        warmth=personality.warmth,
        expertise=personality.expertise,
        humor=personality.humor,
        empathy=personality.empathy,
    )

@app.post("/api/memory/personality", response_model=PersonalityResponse, tags=["记忆管理"])   # 更新AI个性参数接口
async def update_personality(req: PersonalityRequest):
    """更新AI个性参数"""
    personality = await memory_service.get_personality(req.user_id)
    
    if req.warmth is not None:
        personality.warmth = max(0, min(100, req.warmth))
    if req.expertise is not None:
        personality.expertise = max(0, min(100, req.expertise))
    if req.humor is not None:
        personality.humor = max(0, min(100, req.humor))
    if req.empathy is not None:
        personality.empathy = max(0, min(100, req.empathy))
    
    await memory_service.update_personality(req.user_id, personality)
    return PersonalityResponse(
        user_id=req.user_id,
        warmth=personality.warmth,
        expertise=personality.expertise,
        humor=personality.humor,
        empathy=personality.empathy,
    )

@app.post("/api/memory/retrieve", response_model=list[MemoryEventResponse], tags=["记忆管理"])   # 检索相关历史记忆接口
async def retrieve_memory(req: MemoryRetrieveRequest):
    """检索相关历史记忆"""
    events = await memory_service.retrieve_long_term(req.query, req.top_k)
    return [MemoryEventResponse(
        session_id=e.session_id,
        timestamp=e.timestamp,
        user_input=e.user_input,
        agent_response=e.agent_response,
        summary=e.summary,
        topics=e.topics,
        importance=e.importance,
    ) for e in events]

# ── Conversation Endpoints ────────────────────────────────────

@app.post("/api/conversations", response_model=ConversationResponse, tags=["对话管理"])   # 创建新对话会话接口 
async def create_conversation(req: ConversationRequest):
    """创建新对话会话"""
    conversation = await memory_service.create_conversation(
        session_id=req.session_id,
        user_id=req.user_id or "",
        title=req.title or "",
        metadata=req.metadata
    )
    return ConversationResponse(
        session_id=conversation.session_id,
        user_id=conversation.user_id,
        title=conversation.title,
        messages=[],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        metadata=conversation.metadata
    )

@app.get("/api/conversations", response_model=list[ConversationResponse], tags=["对话管理"])   # 获取所有历史对话列表接口
async def list_conversations(user_id: str = "", limit: int = 20, offset: int = 0):
    """获取所有历史对话列表"""
    conversations = await memory_service.list_conversations(user_id=user_id, limit=limit, offset=offset)
    return [ConversationResponse(
        session_id=c.session_id,
        user_id=c.user_id,
        title=c.title,
        messages=[],
        created_at=c.created_at,
        updated_at=c.updated_at,
        metadata=c.metadata
    ) for c in conversations]

@app.post("/api/conversations/search", response_model=list[ConversationResponse], tags=["对话管理"])   # 搜索对话接口
async def search_conversations(req: ConversationSearchRequest):
    """搜索对话（按标题或消息内容）"""
    conversations = await memory_service.search_conversations(
        query=req.query,
        user_id=req.user_id or "",
        limit=req.limit
    )
    return [ConversationResponse(
        session_id=c.session_id,
        user_id=c.user_id,
        title=c.title,
        messages=[],
        created_at=c.created_at,
        updated_at=c.updated_at,
        metadata=c.metadata
    ) for c in conversations]

@app.get("/api/conversations/{session_id}", response_model=ConversationResponse, tags=["对话管理"])   # 获取单个会话详情接口
async def get_conversation(session_id: str):
    """获取单个会话详情（继续对话）"""
    conversation = await memory_service.get_conversation(session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse(
        session_id=conversation.session_id,
        user_id=conversation.user_id,
        title=conversation.title,
        messages=[MessageResponse(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            timestamp=m.timestamp,
            metadata=m.metadata
        ) for m in conversation.messages],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        metadata=conversation.metadata
    )

@app.post("/api/conversations/{session_id}/messages", response_model=MessageResponse, tags=["对话管理"])   # 添加消息到会话接口
async def add_message(session_id: str, req: MessageRequest):
    """添加消息到会话（存储对话）"""
    message = await memory_service.save_message(
        session_id=session_id,
        role=req.role,
        content=req.content,
        message_id=req.message_id or "",
        metadata=req.metadata
    )
    return MessageResponse(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        timestamp=message.timestamp,
        metadata=message.metadata
    )

@app.put("/api/conversations/{session_id}/title", tags=["对话管理"])   # 更新会话标题接口
async def update_conversation_title(session_id: str, title: str):
    """更新会话标题"""
    success = await memory_service.update_conversation_title(session_id, title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "message": "Title updated"}

@app.delete("/api/conversations/{session_id}", tags=["对话管理"])
async def delete_conversation(session_id: str):
    """删除整个会话"""
    success = await memory_service.delete_conversation(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "message": "Conversation deleted"}

@app.delete("/api/conversations/{session_id}/messages/{message_id}", tags=["对话管理"])   # 删除单条消息接口
async def delete_message(session_id: str, message_id: str):
    """删除单条消息"""
    success = await memory_service.delete_message(session_id, message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"success": True, "message": "Message deleted"}

@app.get("/api/health", tags=["系统管理"])      # 健康检查接口
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "service": "SOE Compliance Knowledge Hub",
        "domain": "央国企制度与合规",
        "capabilities": ["制度解析", "条款与风险抽取", "GraphRAG问答", "增量更新"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=settings.api_host, port=settings.api_port, reload=True)   # 启动API服务
    print(f"API service is running on {settings.api_host}:{settings.api_port}")
