"""人物角色记忆系统 - 为每个角色提供独立的记忆和人格"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
import time
from dataclasses import dataclass, field
import uuid

logger = logging.getLogger(__name__)


@dataclass
class CharacterPersonality:
    """人物性格定义"""
    name: str
    description: str
    voice_style: str  # 说话风格
    tone: str          # 语气
    keywords: List[str] = field(default_factory=list)
    avoid_topics: List[str] = field(default_factory=list)
    speaking_patterns: List[str] = field(default_factory=list)


@dataclass
class MemoryItem:
    """记忆项"""
    id: str
    content: str
    timestamp: float
    importance: float = 0.5  # 重要性 0-1
    related_topics: List[str] = field(default_factory=list)
    source: str = "conversation"  # conversation, observation, inference


class CharacterMemory:
    """人物角色记忆系统"""
    
    def __init__(self, character_id: str):
        self.character_id = character_id
        self.short_term_memory: List[MemoryItem] = []  # 最近对话记忆
        self.long_term_memory: List[MemoryItem] = []   # 长期记忆
        self.personality: Optional[CharacterPersonality] = None
        
        # 记忆阈值
        self.short_term_limit = 50  # 短期记忆最大数量
        self.long_term_limit = 500  # 长期记忆最大数量
        
        logger.info(f"人物记忆系统初始化: {character_id}")
    
    def set_personality(self, personality: CharacterPersonality):
        """设置人物性格"""
        self.personality = personality
        logger.info(f"人物 {self.character_id} 设置性格: {personality.name}")
    
    async def add_memory(self, content: str, source: str = "conversation", importance: float = 0.5):
        """添加记忆"""
        memory = MemoryItem(
            id=str(uuid.uuid4()),
            content=content,
            timestamp=time.time(),
            importance=importance,
            source=source
        )
        
        # 添加到短期记忆
        self.short_term_memory.insert(0, memory)
        
        # 限制短期记忆数量
        if len(self.short_term_memory) > self.short_term_limit:
            # 将重要的记忆转移到长期记忆
            important_memories = [
                m for m in self.short_term_memory[-10:]
                if m.importance > 0.7
            ]
            self.long_term_memory.extend(important_memories)
            self.short_term_memory = self.short_term_memory[:self.short_term_limit]
        
        # 限制长期记忆数量
        if len(self.long_term_memory) > self.long_term_limit:
            # 根据重要性排序，保留最重要的
            self.long_term_memory.sort(key=lambda m: -m.importance)
            self.long_term_memory = self.long_term_memory[:self.long_term_limit]
        
        logger.debug(f"人物 {self.character_id} 添加记忆: {content[:30]}...")
    
    async def recall(self, query: str) -> List[MemoryItem]:
        """回忆相关记忆"""
        query_lower = query.lower()
        results = []
        
        # 搜索短期记忆
        for memory in self.short_term_memory:
            if query_lower in memory.content.lower():
                results.append(memory)
        
        # 搜索长期记忆
        for memory in self.long_term_memory:
            if query_lower in memory.content.lower():
                results.append(memory)
        
        # 按重要性和时间排序
        results.sort(key=lambda m: (-m.importance, -m.timestamp))
        return results[:10]  # 返回最多10条
    
    async def get_recent_memories(self, limit: int = 10) -> List[MemoryItem]:
        """获取最近的记忆"""
        return self.short_term_memory[:limit]
    
    async def get_long_term_memories(self, limit: int = 20) -> List[MemoryItem]:
        """获取长期记忆"""
        sorted_memories = sorted(self.long_term_memory, key=lambda m: -m.timestamp)
        return sorted_memories[:limit]
    
    async def forget(self, memory_id: str) -> bool:
        """删除记忆"""
        # 从短期记忆删除
        original_len = len(self.short_term_memory)
        self.short_term_memory = [m for m in self.short_term_memory if m.id != memory_id]
        
        if len(self.short_term_memory) < original_len:
            return True
        
        # 从长期记忆删除
        original_len = len(self.long_term_memory)
        self.long_term_memory = [m for m in self.long_term_memory if m.id != memory_id]
        
        return len(self.long_term_memory) < original_len
    
    def get_personality_prompt(self) -> str:
        """获取性格提示词"""
        if not self.personality:
            return ""
        
        return f"""
你是 {self.personality.name}。
性格描述: {self.personality.description}
说话风格: {self.personality.voice_style}
语气: {self.personality.tone}
常用表达方式: {', '.join(self.personality.speaking_patterns)}
避免话题: {', '.join(self.personality.avoid_topics)}
"""
    
    def get_memory_prompt(self) -> str:
        """获取记忆提示词（用于对话上下文）"""
        recent = self.short_term_memory[:5]
        if not recent:
            return ""
        
        memories = "\n".join([
            f"- {time.strftime('%H:%M', time.localtime(m.timestamp))}: {m.content}"
            for m in recent
        ])
        
        return f"""
最近的记忆:
{memories}
"""


class CharacterMemoryManager:
    """人物记忆管理器"""
    
    def __init__(self):
        self.memories: Dict[str, CharacterMemory] = {}
        
        # 预设人物性格
        self._load_default_personalities()
    
    def _load_default_personalities(self):
        """加载预设人物性格"""
        personalities = {
            "linus_torvalds": CharacterPersonality(
                name="Linus Torvalds",
                description="Linux操作系统之父，直率、技术精湛、对代码质量有极高要求",
                voice_style="直接、坦率、有时带点幽默",
                tone="自信、专业",
                keywords=["Linux", "内核", "开源", "编程", "代码"],
                avoid_topics=["政治", "宗教"],
                speaking_patterns=["实际上...", "让我想想...", "简单来说..."]
            ),
            "libai": CharacterPersonality(
                name="李白",
                description="唐代著名诗人，豪放洒脱，才华横溢",
                voice_style="诗意、浪漫、豪放",
                tone="飘逸、洒脱",
                keywords=["诗", "酒", "月", "山水", "豪情"],
                avoid_topics=["现代科技", "政治"],
                speaking_patterns=["君不见...", "举杯邀明月...", "仰天大笑..."]
            ),
            "goddess": CharacterPersonality(
                name="女神",
                description="优雅、温柔、聪慧的女性形象",
                voice_style="优雅、温柔、知性",
                tone="亲切、关怀",
                keywords=["美丽", "优雅", "生活", "情感", "艺术"],
                avoid_topics=["粗俗", "暴力"],
                speaking_patterns=["亲爱的...", "你觉得呢...", "让我们..."]
            ),
            "john_carmack": CharacterPersonality(
                name="John Carmack",
                description="传奇游戏程序员，id Software创始人",
                voice_style="技术型、简洁、逻辑性强",
                tone="专业、理性",
                keywords=["游戏", "编程", "引擎", "性能", "优化"],
                avoid_topics=["八卦", "闲聊"],
                speaking_patterns=["从技术角度看...", "关键在于...", "优化的关键是..."]
            ),
            "bestfriend": CharacterPersonality(
                name="知心闺蜜",
                description="亲密的女性朋友，善解人意，乐于倾听",
                voice_style="亲切、温暖、支持",
                tone="关心、鼓励",
                keywords=["朋友", "情感", "生活", "分享", "支持"],
                avoid_topics=["攻击性语言", "负面评价"],
                speaking_patterns=["亲爱的...", "我理解...", "加油哦..."]
            ),
            "first_love": CharacterPersonality(
                name="初恋",
                description="青涩纯真的初恋对象，温柔甜蜜",
                voice_style="羞涩、温柔、甜蜜",
                tone="害羞、深情",
                keywords=["爱情", "回忆", "甜蜜", "青春"],
                avoid_topics=["争吵", "分手"],
                speaking_patterns=["那个时候...", "还记得吗...", "好想..."]
            )
        }
        
        for char_id, personality in personalities.items():
            memory = CharacterMemory(char_id)
            memory.set_personality(personality)
            self.memories[char_id] = memory
        
        logger.info(f"已加载 {len(personalities)} 个人物性格")
    
    def get_memory(self, character_id: str) -> CharacterMemory:
        """获取人物记忆"""
        if character_id not in self.memories:
            self.memories[character_id] = CharacterMemory(character_id)
        
        return self.memories[character_id]
    
    async def add_memory_to_character(self, character_id: str, content: str, source: str = "conversation"):
        """向人物添加记忆"""
        memory = self.get_memory(character_id)
        await memory.add_memory(content, source)
    
    async def get_character_response_context(self, character_id: str) -> str:
        """获取人物响应上下文（性格+记忆）"""
        memory = self.get_memory(character_id)
        return memory.get_personality_prompt() + memory.get_memory_prompt()


# 全局人物记忆管理器
character_memory_manager = CharacterMemoryManager()
