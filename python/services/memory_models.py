"""
记忆数据模型 — 定义记忆系统的数据结构

包含三层记忆的数据模型:
  1. MemoryEvent: 单次交互记忆（短期+长期）
  2. UserProfile: 用户画像
  3. Personality: 个性化参数（AI性格）
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MemoryEvent:
    """单次交互记忆（比如用户问一句话，AI答一句话）"""
    session_id: str
    user_input: str
    agent_response: str
    summary: str = ""
    topics: List[str] = field(default_factory=list)
    importance: float = 1.0
    timestamp: str = ""
    embedding: List[float] = field(default_factory=list)
    
    def __post_init__(self):
        if self.timestamp == "":
            self.timestamp = datetime.now().isoformat()


@dataclass
class UserProfile:
    """用户画像（存储用户的基本信息）"""
    user_id: str
    name: str = ""
    background: str = ""
    preferences: Dict[str, Any] = field(default_factory=dict)
    interaction_count: int = 0
    last_active: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if self.created_at == "":
            self.created_at = datetime.now().isoformat()
        if self.last_active == "":
            self.last_active = datetime.now().isoformat()


@dataclass
class Personality:
    """个性化参数（AI的性格，会自动调整）"""
    warmth: float = 50.0      # 热情度（0-100）
    expertise: float = 70.0   # 专业度（0-100）
    humor: float = 30.0       # 幽默感（0-100）
    empathy: float = 50.0     # 共情力（0-100）
    
    def to_dict(self):
        return {
            "warmth": self.warmth,
            "expertise": self.expertise,
            "humor": self.humor,
            "empathy": self.empathy
        }
    
    def adjust(self, feedback: Dict[str, float]):
        """根据用户反馈调整个性参数"""
        for key, delta in feedback.items():
            if hasattr(self, key):
                current = getattr(self, key)
                new_value = max(0, min(100, current + delta))
                setattr(self, key, new_value)
        return self


@dataclass
class MemoryContext:
    """整合后的对话上下文"""
    short_term: str
    long_term: str
    profile: str
    personality: Dict[str, float]


@dataclass
class Message:
    """单条消息"""
    id: str = ""
    session_id: str = ""
    role: str = "user"  # user | assistant | system
    content: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.timestamp == "":
            self.timestamp = datetime.now().isoformat()


@dataclass
class Conversation:
    """对话会话"""
    session_id: str
    user_id: str = ""
    title: str = ""
    messages: List[Message] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.created_at == "":
            self.created_at = datetime.now().isoformat()
        if self.updated_at == "":
            self.updated_at = datetime.now().isoformat()
    
    def add_message(self, message: Message):
        """添加消息到会话"""
        message.session_id = self.session_id
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()
    
    def get_latest_messages(self, limit: int = 10) -> List[Message]:
        """获取最近的消息"""
        return self.messages[-limit:]
    
    def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """根据ID获取消息"""
        for msg in self.messages:
            if msg.id == message_id:
                return msg
        return None
    
    def remove_message(self, message_id: str) -> bool:
        """删除单条消息"""
        for i, msg in enumerate(self.messages):
            if msg.id == message_id:
                del self.messages[i]
                self.updated_at = datetime.now().isoformat()
                return True
        return False