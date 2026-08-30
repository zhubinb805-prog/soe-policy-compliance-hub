"""
记忆服务 — 三层记忆管理系统

核心能力:
  1. 短期记忆（最近N轮对话，内存存储）
  2. 长期记忆（历史对话，SQLite持久化）
  3. 用户画像（存储用户信息）
  4. 个性参数（AI性格调整）
  5. 反思机制（自动调整个性）
"""

import json
import pickle
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from config import settings
from .memory_models import MemoryContext, MemoryEvent, Personality, UserProfile, Conversation, Message


class MemoryService:
    """三层记忆管理系统：短期记忆+长期记忆+用户画像"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.memory_db_path
        self.short_term: List[MemoryEvent] = []
        self._init_database()
    
    def _init_database(self):
        """初始化SQLite数据库，创建表格"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TEXT,
                user_input TEXT,
                agent_response TEXT,
                summary TEXT,
                topics TEXT,
                importance REAL,
                embedding BLOB,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                name TEXT,
                background TEXT,
                preferences TEXT,
                interaction_count INTEGER,
                last_active TEXT,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personality (
                user_id TEXT PRIMARY KEY,
                warmth REAL,
                expertise REAL,
                humor REAL,
                empathy REAL,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                goal TEXT,
                status TEXT,
                progress REAL,
                last_updated TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                metadata TEXT,
                FOREIGN KEY (session_id) REFERENCES conversations(session_id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
        conn.close()
    
    async def add_short_term(self, event: MemoryEvent):
        """添加短期记忆，超出窗口自动丢弃"""
        self.short_term.append(event)
        if len(self.short_term) > settings.short_term_window:
            self.short_term.pop(0)
    
    def get_short_term(self) -> List[MemoryEvent]:
        """获取短期记忆"""
        return self.short_term.copy()
    
    async def add_long_term(self, event: MemoryEvent):
        """添加长期记忆（存入SQLite数据库）"""
        if not event.summary:
            event.summary = self._generate_summary(event)
        
        text_to_embed = f"{event.user_input} {event.agent_response} {event.summary}"
        if text_to_embed.strip():
            from langchain_openai import OpenAIEmbeddings
            
            if "dashscope" in settings.openai_base_url.lower():
                from .vector_store import DashScopeEmbeddings
                embedder = DashScopeEmbeddings(
                    api_key=settings.openai_api_key,
                    model=settings.embedding_model,
                )
            else:
                embedder = OpenAIEmbeddings(
                    model=settings.embedding_model,
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                )
            event.embedding = await embedder.aembed_query(text_to_embed.strip())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memory_events 
            (session_id, timestamp, user_input, agent_response, summary, topics, importance, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.session_id,
            event.timestamp,
            event.user_input,
            event.agent_response,
            event.summary,
            json.dumps(event.topics, ensure_ascii=False),
            event.importance,
            pickle.dumps(event.embedding) if event.embedding else None,
        ))
        conn.commit()
        conn.close()
    
    async def retrieve_long_term(self, query: str, top_k: int = 5) -> List[MemoryEvent]:
        """检索长期记忆（根据用户的问题，找到相关的历史记忆）"""
        if not query.strip():
            query_embedding = [0.0] * 1536
        else:
            from langchain_openai import OpenAIEmbeddings
            
            if "dashscope" in settings.openai_base_url.lower():
                from .vector_store import DashScopeEmbeddings
                embedder = DashScopeEmbeddings(
                    api_key=settings.openai_api_key,
                    model=settings.embedding_model,
                )
            else:
                embedder = OpenAIEmbeddings(
                    model=settings.embedding_model,
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                )
            query_embedding = await embedder.aembed_query(query.strip())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_id, timestamp, user_input, agent_response, 
                   summary, topics, importance, embedding
            FROM memory_events
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return []
        
        scored_memories = []
        for row in rows:
            try:
                embedding = pickle.loads(row[7]) if row[7] else [0.0] * 1536
            except:
                embedding = [0.0] * 1536
            
            similarity = np.dot(query_embedding, embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(embedding) + 1e-8
            )
            
            memory = MemoryEvent(
                session_id=row[0],
                timestamp=row[1],
                user_input=row[2],
                agent_response=row[3],
                summary=row[4],
                topics=json.loads(row[5]) if row[5] else [],
                importance=row[6]
            )
            scored_memories.append((similarity * memory.importance, memory))
        
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored_memories[:top_k]]
    
    @staticmethod
    def _generate_summary(event: MemoryEvent) -> str:
        """生成交互摘要"""
        combined = f"用户：{event.user_input}\n助手：{event.agent_response}"
        if len(combined) > 200:
            return combined[:200] + "..."
        return combined
    
    async def update_user_profile(self, user_id: str, profile: UserProfile):
        """更新用户画像"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_profiles 
            (user_id, name, background, preferences, interaction_count, last_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            profile.name,
            profile.background,
            json.dumps(profile.preferences, ensure_ascii=False),
            profile.interaction_count,
            profile.last_active,
            profile.created_at
        ))
        conn.commit()
        conn.close()
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, name, background, preferences, interaction_count, last_active, created_at
            FROM user_profiles
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return UserProfile(
                user_id=row[0],
                name=row[1] or "",
                background=row[2] or "",
                preferences=json.loads(row[3]) if row[3] else {},
                interaction_count=row[4],
                last_active=row[5],
                created_at=row[6]
            )
        return None
    
    async def get_personality(self, user_id: str) -> Personality:
        """获取AI的个性参数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT warmth, expertise, humor, empathy
            FROM personality
            WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Personality(
                warmth=row[0],
                expertise=row[1],
                humor=row[2],
                empathy=row[3]
            )
        return Personality()
    
    async def update_personality(self, user_id: str, personality: Personality):
        """更新AI的个性参数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO personality
            (user_id, warmth, expertise, humor, empathy, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            personality.warmth,
            personality.expertise,
            personality.humor,
            personality.empathy,
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
    
    async def get_conversation_context(self, query: str, user_id: str, session_id: str) -> MemoryContext:
        """获取完整的对话上下文（整合三层记忆）"""
        short_term = self.get_short_term()
        short_term_text = "\n".join([
            f"用户: {m.user_input}\n助手: {m.agent_response}"
            for m in short_term[-3:]
        ])
        
        long_term = await self.retrieve_long_term(query, settings.long_term_top_k)
        long_term_text = "\n\n".join([
            f"[历史记忆] {m.summary}" for m in long_term
        ])
        
        profile = await self.get_user_profile(user_id)
        profile_text = ""
        if profile:
            profile_text = f"""
用户信息：
- 称呼：{profile.name}
- 背景：{profile.background}
- 偏好：{json.dumps(profile.preferences, ensure_ascii=False)}
- 已交互次数：{profile.interaction_count}
"""
        
        personality = await self.get_personality(user_id)
        
        return MemoryContext(
            short_term=short_term_text,
            long_term=long_term_text,
            profile=profile_text,
            personality=personality.to_dict()
        )
    
    # ==================== 对话管理模块 ====================
    
    async def create_conversation(self, session_id: str, user_id: str = "", title: str = "", metadata: Dict[str, Any] = None) -> Conversation:
        """创建新对话会话"""
        conversation = Conversation(
            session_id=session_id,
            user_id=user_id,
            title=title,
            metadata=metadata or {}
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO conversations 
            (session_id, user_id, title, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            conversation.session_id,
            conversation.user_id,
            conversation.title,
            json.dumps(conversation.metadata, ensure_ascii=False),
            conversation.created_at,
            conversation.updated_at
        ))
        conn.commit()
        conn.close()
        
        return conversation
    
    async def save_message(self, session_id: str, role: str, content: str, message_id: str = "", metadata: Dict[str, Any] = None) -> Message:
        """保存单条消息到会话"""
        message = Message(
            id=message_id or f"msg_{datetime.now().timestamp()}",
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO messages 
            (id, session_id, role, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            message.id,
            message.session_id,
            message.role,
            message.content,
            message.timestamp,
            json.dumps(message.metadata, ensure_ascii=False)
        ))
        
        cursor.execute("""
            UPDATE conversations 
            SET updated_at = ? 
            WHERE session_id = ?
        """, (message.timestamp, session_id))
        
        conn.commit()
        conn.close()
        
        return message
    
    async def get_conversation(self, session_id: str) -> Optional[Conversation]:
        """获取单个会话详情"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT session_id, user_id, title, metadata, created_at, updated_at
            FROM conversations
            WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        conversation = Conversation(
            session_id=row[0],
            user_id=row[1] or "",
            title=row[2] or "",
            metadata=json.loads(row[3]) if row[3] else {},
            created_at=row[4],
            updated_at=row[5]
        )
        
        cursor.execute("""
            SELECT id, role, content, timestamp, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,))
        
        for msg_row in cursor.fetchall():
            message = Message(
                id=msg_row[0],
                session_id=session_id,
                role=msg_row[1],
                content=msg_row[2],
                timestamp=msg_row[3],
                metadata=json.loads(msg_row[4]) if msg_row[4] else {}
            )
            conversation.messages.append(message)
        
        conn.close()
        return conversation
    
    async def list_conversations(self, user_id: str = "", limit: int = 20, offset: int = 0) -> List[Conversation]:
        """获取会话列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if user_id:
            cursor.execute("""
                SELECT session_id, user_id, title, metadata, created_at, updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
        else:
            cursor.execute("""
                SELECT session_id, user_id, title, metadata, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
        
        conversations = []
        for row in cursor.fetchall():
            conversation = Conversation(
                session_id=row[0],
                user_id=row[1] or "",
                title=row[2] or "",
                metadata=json.loads(row[3]) if row[3] else {},
                created_at=row[4],
                updated_at=row[5]
            )
            conversations.append(conversation)
        
        conn.close()
        return conversations
    
    async def search_conversations(self, query: str, user_id: str = "", limit: int = 20) -> List[Conversation]:
        """搜索会话（按标题或消息内容）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        search_pattern = f"%{query}%"
        
        if user_id:
            cursor.execute("""
                SELECT DISTINCT c.session_id, c.user_id, c.title, c.metadata, c.created_at, c.updated_at
                FROM conversations c
                LEFT JOIN messages m ON c.session_id = m.session_id
                WHERE c.user_id = ? AND (c.title LIKE ? OR m.content LIKE ?)
                ORDER BY c.updated_at DESC
                LIMIT ?
            """, (user_id, search_pattern, search_pattern, limit))
        else:
            cursor.execute("""
                SELECT DISTINCT c.session_id, c.user_id, c.title, c.metadata, c.created_at, c.updated_at
                FROM conversations c
                LEFT JOIN messages m ON c.session_id = m.session_id
                WHERE c.title LIKE ? OR m.content LIKE ?
                ORDER BY c.updated_at DESC
                LIMIT ?
            """, (search_pattern, search_pattern, limit))
        
        conversations = []
        for row in cursor.fetchall():
            conversation = Conversation(
                session_id=row[0],
                user_id=row[1] or "",
                title=row[2] or "",
                metadata=json.loads(row[3]) if row[3] else {},
                created_at=row[4],
                updated_at=row[5]
            )
            conversations.append(conversation)
        
        conn.close()
        return conversations
    
    async def delete_conversation(self, session_id: str) -> bool:
        """删除整个会话"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        
        success = cursor.rowcount > 0
        conn.close()
        
        return success
    
    async def delete_message(self, session_id: str, message_id: str) -> bool:
        """删除单条消息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM messages 
            WHERE session_id = ? AND id = ?
        """, (session_id, message_id))
        conn.commit()
        
        success = cursor.rowcount > 0
        conn.close()
        
        return success
    
    async def update_conversation_title(self, session_id: str, title: str) -> bool:
        """更新会话标题"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE conversations 
            SET title = ?, updated_at = ? 
            WHERE session_id = ?
        """, (title, datetime.now().isoformat(), session_id))
        conn.commit()
        
        success = cursor.rowcount > 0
        conn.close()
        
        return success