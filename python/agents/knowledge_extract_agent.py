"""
知识抽取 Agent — 从文档块中提取实体、关系、事件，构建知识图谱三元组

核心能力:
  1. 命名实体识别 (NER)
  2. 关系抽取 (RE)
  3. 事件抽取
  4. 三元组生成 → 写入 Neo4j
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.doc_parser_agent import DocumentChunk
from config import settings

ENTITY_TYPES = {
    "Policy", "Clause", "Regulation", "Department", "Role", "Process",
    "Risk", "Control", "Organization", "Event", "Time", "Concept",
}
RELATION_TYPES = {
    "contains_clause", "governed_by", "applies_to", "owned_by", "requires",
    "mitigates", "conflicts_with", "supersedes", "related_to", "part_of",
}
ENTITY_PROPERTY_KEYS = {"scope", "effective_date", "expiry_date", "version", "risk_level", "clause_number"}

EXTRACTION_SYSTEM_PROMPT = """\
你是央国企制度与合规知识抽取专家。给定一段制度、监管或内控文本，请提取可审计、可追溯的结构化知识：
1. **实体 (entities)**：制度文件、制度条款、监管要求、责任部门、岗位、业务流程、风险事项、控制措施、组织机构、时间等
2. **关系 (relations)**：实体之间的关系，用三元组 (头实体, 关系, 尾实体) 表示
3. **事件 (events)**：文本中提到的事件，包含触发词和参与者

请严格按照以下 JSON 格式返回：
{
  "entities": [
    {"name": "实体名", "type": "实体类型", "description": "简短描述", "scope": "适用范围", "effective_date": "生效日期", "version": "版本", "risk_level": "风险等级"}
  ],
  "relations": [
    {"head": "头实体", "relation": "关系类型", "tail": "尾实体", "confidence": 0.95}
  ],
  "events": [
    {"trigger": "触发词", "type": "事件类型", "participants": ["参与者1"]}
  ]
}

注意:
- 实体类型包括: Policy, Clause, Regulation, Department, Role, Process, Risk, Control, Organization, Event, Time, Concept
- 关系类型包括: contains_clause, governed_by, applies_to, owned_by, requires, mitigates, conflicts_with, supersedes, related_to, part_of
- confidence 为 0-1 之间的浮点数
- 只返回 JSON，不要包含其他文字
"""


@dataclass
class Entity:
    name: str
    type: str
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def node_label(self) -> str:
        return self.type.replace(" ", "_")


@dataclass
class Relation:
    head: str
    relation: str
    tail: str
    confidence: float = 0.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeEvent:
    trigger: str
    type: str
    participants: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    entities: list[Entity]
    relations: list[Relation]
    events: list[KnowledgeEvent]
    source_chunk_id: str = ""


class KnowledgeExtractAgent:
    """
    知识抽取 Agent

    工作流:
      receive_chunks → extract_per_chunk → deduplicate → resolve_entities → output_triples
    """

    BATCH_SIZE = 5

    def __init__(self) -> None:
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
        )

    # ── public API ───────────────────────────────────────────

    async def extract(self, chunks: list[DocumentChunk]) -> list[ExtractionResult]:
        """从一组文档块中抽取知识"""
        results: list[ExtractionResult] = []
        for i in range(0, len(chunks), self.BATCH_SIZE):
            batch = chunks[i : i + self.BATCH_SIZE]
            for chunk in batch:
                result = await self._extract_from_chunk(chunk)
                results.append(result)
        merged = self._deduplicate(results)
        return merged

    async def extract_single(self, text: str, chunk_id: str = "") -> ExtractionResult:
        """从单段文本中抽取知识"""
        return await self._extract_from_text(text, chunk_id)

    # ── core extraction ──────────────────────────────────────

    async def _extract_from_chunk(self, chunk: DocumentChunk) -> ExtractionResult:
        return await self._extract_from_text(chunk.content, chunk.chunk_id)

    async def _extract_from_text(self, text: str, source_id: str) -> ExtractionResult:
        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"请从以下文本中抽取知识：\n\n{text}"),
        ]
        resp = await self.llm.ainvoke(messages)
        return self._parse_response(resp.content, source_id)

    def _parse_response(self, raw: str, source_id: str) -> ExtractionResult:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                cleaned = cleaned.rsplit("```", 1)[0]
            data = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return ExtractionResult(entities=[], relations=[], events=[], source_chunk_id=source_id)

        entities = [
            Entity(
                name=e.get("name", ""),
                type=e.get("type") if e.get("type") in ENTITY_TYPES else "Concept",
                description=e.get("description", ""),
                properties={k: v for k, v in e.items() if k in ENTITY_PROPERTY_KEYS and v not in (None, "")},
            )
            for e in data.get("entities", [])
            if e.get("name")
        ]
        relations = [
            Relation(
                head=r.get("head", ""),
                relation=r.get("relation") if r.get("relation") in RELATION_TYPES else "related_to",
                tail=r.get("tail", ""),
                confidence=float(r.get("confidence", 0.5)),
                properties={},
            )
            for r in data.get("relations", [])
            if r.get("head") and r.get("tail")
        ]
        events = [
            KnowledgeEvent(
                trigger=ev.get("trigger", ""),
                type=ev.get("type", ""),
                participants=ev.get("participants", []),
            )
            for ev in data.get("events", [])
        ]
        return ExtractionResult(
            entities=entities,
            relations=relations,
            events=events,
            source_chunk_id=source_id,
        )

    # ── deduplication & entity resolution ────────────────────

    @staticmethod
    def _deduplicate(results: list[ExtractionResult]) -> list[ExtractionResult]:
        """
        跨 chunk 去重: 同名同类型实体合并，关系去重
        """
        seen_entities: dict[str, Entity] = {}
        seen_relations: set[tuple[str, str, str]] = set()
        deduped: list[ExtractionResult] = []

        for result in results:
            unique_entities: list[Entity] = []
            for ent in result.entities:
                key = f"{ent.name}::{ent.type}"
                if key not in seen_entities:
                    seen_entities[key] = ent
                    unique_entities.append(ent)

            unique_relations: list[Relation] = []
            for rel in result.relations:
                key = (rel.head, rel.relation, rel.tail)
                if key not in seen_relations:
                    seen_relations.add(key)
                    unique_relations.append(rel)

            deduped.append(ExtractionResult(
                entities=unique_entities,
                relations=unique_relations,
                events=result.events,
                source_chunk_id=result.source_chunk_id,
            ))
        return deduped
