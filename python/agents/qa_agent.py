"""
问答 Agent — 混合检索 (Vector + Graph) + 多跳推理 + 答案生成 + 记忆系统

核心能力:
  1. 意图识别 & 查询改写
  2. 向量检索 (语义相似度)
  3. 图谱检索 (Cypher 查询 / 子图遍历)
  4. 混合排序 & 重排序
  5. 基于检索结果的答案生成（带引用来源）
  6. 记忆系统集成（短期+长期记忆、用户画像、个性化）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import settings
from services.memory_models import MemoryEvent, Personality, UserProfile


class QueryIntent(str, Enum):
    FACTOID = "factoid"           # 事实型问题
    ANALYTICAL = "analytical"     # 分析型问题
    COMPARATIVE = "comparative"   # 对比型问题
    PROCEDURAL = "procedural"     # 流程型问题
    EXPLORATORY = "exploratory"   # 探索型问题


@dataclass
class RetrievedContext:
    content: str
    source: str
    score: float
    retrieval_type: str  # "vector" | "graph" | "hybrid"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QAResult:
    question: str
    answer: str
    contexts: list[RetrievedContext]
    intent: QueryIntent
    confidence: float
    reasoning_steps: list[str] = field(default_factory=list)


INTENT_PROMPT = """\
你是一个查询意图分类器。根据用户问题，返回意图类别（只返回类别名）：
- factoid: 事实型（谁/什么/哪里/何时）
- analytical: 分析型（为什么/怎么理解）
- comparative: 对比型（A和B有什么区别）
- procedural: 流程型（怎么做/步骤）
- exploratory: 探索型（有哪些/概述）
"""

QUERY_REWRITE_PROMPT = """\
你是一个查询改写专家。将用户问题改写为更适合检索的形式。
要求：
1. 提取核心实体和关键词
2. 生成 1-3 个检索查询
3. 返回 JSON: {"queries": ["查询1", "查询2"], "entities": ["实体1"], "keywords": ["关键词1"]}
"""

CYPHER_GENERATION_PROMPT = """\
你是央国企制度与合规知识图谱的 Cypher 查询专家。根据用户问题和提取的实体，生成只读 Cypher 查询。

知识图谱 Schema:
- 所有节点标签均为 Entity，通过 type 属性区分: Policy, Clause, Regulation, Department, Role, Process, Risk, Control, Organization, Event, Time, Concept
- 关系类型: contains_clause, governed_by, applies_to, owned_by, requires, mitigates, conflicts_with, supersedes, related_to, part_of
- 节点属性: name, type, description, source, version, effective_date, expiry_date, risk_level, scope
- 示例: MATCH (p:Entity {type: 'Policy'})-[:CONTAINS_CLAUSE]->(c:Entity {type: 'Clause'}) RETURN p, c

生成 1-2 条 Cypher 查询，返回 JSON: {"queries": ["MATCH ...", "MATCH ..."]}
只返回 JSON，不要其他文字。
"""

ANSWER_PROMPT = """\
你是央国企制度与合规问答助手。根据检索到的上下文回答问题，面向咨询项目交付场景。

要求：
1. 答案必须基于提供的上下文，不要编造
2. 如果上下文信息不足，明确告知用户
3. 引用信息来源（如 [来源: xxx]）
4. 如果涉及多个信息源，综合分析后给出结论
5. 优先输出：结论、适用范围/责任部门、制度版本与生效时间、风险提示、原文依据（文件名+页码或条款）
6. 明确区分“制度明确规定”和“基于材料的推断”；材料不足时不要臆测
7. 保持专业、准确、简洁
"""

MEMORY_ANSWER_PROMPT = """\
你是央国企制度与合规咨询助手，正在与用户进行多轮对话。记忆只用于衔接问题和调整表达，不得改变制度事实或合规结论。

【你的个性特征】
- 热情度：{warmth}/100
- 专业度：{expertise}/100
- 幽默感：{humor}/100
- 共情力：{empathy}/100

【风格要求】
{style_instructions}

【用户画像】
{profile}

【近期对话（短期记忆）】
{short_term}

【相关历史记忆（长期记忆）】
{long_term}

【知识库参考】
{knowledge_context}

【当前问题】
{question}

请基于以上所有信息，结合知识库内容，用符合你个性的方式回答用户的问题。
重点注意：
1. 一定要体现你对用户的了解和记忆，比如叫用户的名字，衔接历史话题，不要像第一次聊天；
2. 回答要贴合用户的专业背景，不要讲用户已经知道的内容，也不要讲太超出用户水平的内容；
3. 不用刻意堆砌知识点，实用、易懂为主；
4. 引用信息来源（如 [来源: 文件名，第x页/第x条]）；
5. 优先输出结论、适用范围、责任部门、版本/生效日期、风险提示和原文依据；
6. 明确区分制度原文和推断，材料不足时不得编造；
7. 合规结论保持克制、专业，不使用幽默或情绪化表达。
"""


class QAAgent:
    """
    问答 Agent

    工作流:
      query → intent_classify → rewrite → parallel_retrieve → memory_retrieve → rerank → generate_answer → memory_store
    """

    def __init__(
        self,
        vector_store: Any = None,
        knowledge_graph: Any = None,
        memory_service: Any = None,
    ) -> None:
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
        )
        self.vector_store = vector_store
        self.knowledge_graph = knowledge_graph
        self.memory_service = memory_service
        self.session_id = datetime.now().strftime("%Y%m%d%H%M%S")
        self.user_id = "default_user"
        self.interaction_count = 0
        
        self.profile: UserProfile = UserProfile(user_id=self.user_id)
        self.personality: Personality = Personality()

    async def init_memory(self):
        """初始化记忆相关数据"""
        if self.memory_service:
            self.profile = await self.memory_service.get_user_profile(self.user_id) or UserProfile(user_id=self.user_id)
            self.personality = await self.memory_service.get_personality(self.user_id) or Personality()
            await self.memory_service.update_user_profile(self.user_id, self.profile)

    def set_session_context(self, session_id: str = None, user_id: str = None):
        """设置会话上下文"""
        if session_id:
            self.session_id = session_id
        if user_id:
            self.user_id = user_id

    # ── public API ───────────────────────────────────────────

    async def answer(self, question: str) -> QAResult:
        """完整问答流程"""
        self.interaction_count += 1
        
        intent = await self._classify_intent(question)
        rewritten = await self._rewrite_query(question)

        vector_contexts = await self._vector_retrieve(rewritten)
        graph_contexts = await self._graph_retrieve(question, rewritten)

        all_contexts = self._hybrid_rerank(vector_contexts + graph_contexts)
        top_contexts = all_contexts[:8]

        answer_text, reasoning = await self._generate_answer(question, top_contexts, intent)

        await self._store_memory(question, answer_text)
        await self._update_profile(question)

        return QAResult(
            question=question,
            answer=answer_text,
            contexts=top_contexts,
            intent=intent,
            confidence=self._calc_confidence(top_contexts),
            reasoning_steps=reasoning,
        )

    # ── memory management ────────────────────────────────────

    async def _store_memory(self, user_input: str, agent_response: str):
        """存储对话记忆"""
        if not self.memory_service:
            return

        event = MemoryEvent(
            session_id=self.session_id,
            user_input=user_input,
            agent_response=agent_response,
            importance=1.0
        )

        await self.memory_service.add_short_term(event)

        if self.interaction_count % 2 == 0:
            await self.memory_service.add_long_term(event)

    async def _update_profile(self, user_input: str):
        """更新用户画像"""
        if not self.memory_service:
            return

        self.profile.interaction_count += 1
        self.profile.last_active = datetime.now().isoformat()

        name_match = re.search(r"叫([^，。\s]+)", user_input)
        if name_match and not self.profile.name:
            self.profile.name = name_match.group(1)

        bg_match = re.search(r"是([^，。\s]+)", user_input)
        if bg_match and not self.profile.background:
            self.profile.background = bg_match.group(1)

        await self.memory_service.update_user_profile(self.user_id, self.profile)

    # ── intent classification ────────────────────────────────

    async def _classify_intent(self, question: str) -> QueryIntent:
        messages = [
            SystemMessage(content=INTENT_PROMPT),
            HumanMessage(content=question),
        ]
        resp = await self.llm.ainvoke(messages)
        raw = resp.content.strip().lower()
        for intent in QueryIntent:
            if intent.value in raw:
                return intent
        return QueryIntent.FACTOID

    # ── query rewriting ──────────────────────────────────────

    async def _rewrite_query(self, question: str) -> dict:
        import json
        messages = [
            SystemMessage(content=QUERY_REWRITE_PROMPT),
            HumanMessage(content=question),
        ]
        resp = await self.llm.ainvoke(messages)
        try:
            cleaned = resp.content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {"queries": [question], "entities": [], "keywords": []}

    # ── vector retrieval ─────────────────────────────────────

    async def _vector_retrieve(self, rewritten: dict) -> list[RetrievedContext]:
        if not self.vector_store:
            return []

        contexts: list[RetrievedContext] = []
        for query in rewritten.get("queries", []):
            results = await self.vector_store.search(query, top_k=5)
            for doc, score in results:
                contexts.append(RetrievedContext(
                    content=doc.get("content", ""),
                    source=doc.get("source", "vector_store"),
                    score=score,
                    retrieval_type="vector",
                    metadata=doc.get("metadata", {}),
                ))
        return contexts

    # ── graph retrieval ──────────────────────────────────────

    async def _graph_retrieve(self, question: str, rewritten: dict) -> list[RetrievedContext]:
        if not self.knowledge_graph:
            return []

        import json
        entities = rewritten.get("entities", [])
        messages = [
            SystemMessage(content=CYPHER_GENERATION_PROMPT),
            HumanMessage(content=f"问题: {question}\n实体: {entities}"),
        ]
        resp = await self.llm.ainvoke(messages)
        try:
            cleaned = resp.content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            cypher_data = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            cypher_data = {"queries": []}

        contexts: list[RetrievedContext] = []
        for cypher in cypher_data.get("queries", []):
            if not self._is_read_only_cypher(cypher):
                continue
            try:
                records = await self.knowledge_graph.execute_cypher(cypher)
                for record in records:
                    contexts.append(RetrievedContext(
                        content=str(record),
                        source="knowledge_graph",
                        score=0.8,
                        retrieval_type="graph",
                        metadata={"cypher": cypher},
                    ))
            except Exception:
                continue
        return contexts

    @staticmethod
    def _is_read_only_cypher(cypher: str) -> bool:
        """Reject model-generated Cypher that can mutate data or call procedures."""
        forbidden = r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL|FOREACH)\b"
        return bool(cypher.strip()) and re.search(forbidden, cypher, flags=re.IGNORECASE) is None

    # ── hybrid reranking ─────────────────────────────────────

    @staticmethod
    def _hybrid_rerank(contexts: list[RetrievedContext]) -> list[RetrievedContext]:
        """
        混合重排序：向量分数 + 图谱分数加权
        图谱检索结果天然带有结构化关系，给予略高权重
        """
        weight_map = {"vector": 1.0, "graph": 1.2, "hybrid": 1.1}
        for ctx in contexts:
            ctx.score *= weight_map.get(ctx.retrieval_type, 1.0)

        seen: set[str] = set()
        unique: list[RetrievedContext] = []
        for ctx in contexts:
            key = ctx.content[:100]
            if key not in seen:
                seen.add(key)
                unique.append(ctx)

        unique.sort(key=lambda c: c.score, reverse=True)
        return unique

    # ── answer generation ────────────────────────────────────

    async def _generate_answer(
        self,
        question: str,
        contexts: list[RetrievedContext],
        intent: QueryIntent,
    ) -> tuple[str, list[str]]:
        knowledge_context = "\n\n".join(
            f"[来源 {i+1}: {c.source} | 页码: {c.metadata.get('page') or '未标注'} | "
            f"类型: {c.retrieval_type} | 分数: {c.score:.2f}]\n{c.content}"
            for i, c in enumerate(contexts)
        )
        reasoning_steps = [
            f"识别问题意图: {intent.value}",
            f"检索到 {len(contexts)} 条相关上下文",
            f"向量检索: {sum(1 for c in contexts if c.retrieval_type == 'vector')} 条",
            f"图谱检索: {sum(1 for c in contexts if c.retrieval_type == 'graph')} 条",
        ]

        if self.memory_service:
            memory_context = await self.memory_service.get_conversation_context(
                question, self.user_id, self.session_id
            )
            
            style_instructions = self._build_style_instructions(self.personality)
            
            formatted_prompt = MEMORY_ANSWER_PROMPT.format(
                warmth=self.personality.warmth,
                expertise=self.personality.expertise,
                humor=self.personality.humor,
                empathy=self.personality.empathy,
                style_instructions=style_instructions,
                profile=memory_context.profile,
                short_term=memory_context.short_term,
                long_term=memory_context.long_term,
                knowledge_context=knowledge_context,
                question=question
            )
            
            reasoning_steps.append("检索到记忆上下文")
        else:
            formatted_prompt = f"{ANSWER_PROMPT}\n\n上下文信息:\n{knowledge_context}\n\n用户问题: {question}"

        messages = [
            SystemMessage(content=formatted_prompt),
        ]
        resp = await self.llm.ainvoke(messages)
        reasoning_steps.append("答案生成完成")
        return resp.content, reasoning_steps

    @staticmethod
    def _build_style_instructions(personality: Personality) -> str:
        """根据性格参数构建风格指令"""
        instructions = []
        
        if personality.warmth > 70:
            instructions.append("语气热情友好，多使用亲切的表达，可以适当加入表情符号，不用太严肃。")
        elif personality.warmth < 30:
            instructions.append("保持简洁直接，不过分热情，专注于回答问题，不用多余的寒暄。")
        
        if personality.expertise > 80:
            instructions.append("回答要专业深入，可以包含技术术语和详细解释，适合有一定专业基础的用户。")
        elif personality.expertise < 40:
            instructions.append("用通俗易懂的语言解释，避免专业术语，把复杂问题讲简单，适合新手。")
        
        if personality.humor > 60:
            instructions.append("适当加入幽默元素，用轻松的语气回答，比如加入简单的调侃、生活化的比喻。")
        
        if personality.empathy > 70:
            instructions.append("多关注用户的情绪，表达理解和共情，比如用户说难，就安慰鼓励，不要只讲知识点。")
        
        return "\n".join(instructions) if instructions else "保持自然专业的语气，贴合用户的专业背景，回答准确、实用。"

    @staticmethod
    def _calc_confidence(contexts: list[RetrievedContext]) -> float:
        if not contexts:
            return 0.0
        avg_score = sum(c.score for c in contexts) / len(contexts)
        return min(avg_score, 1.0)
