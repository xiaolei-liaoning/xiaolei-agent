"""自我进化引擎 — 定期总结任务经验，提炼优化建议

触发时机：
  - 每次有新的 experience 条目超过阈值（10条未总结）
  - 或距离上次总结超过 24 小时

流程：
  1. 从 VectorMemoryStore 读取未总结的 experience 条目
  2. 读取已有 insight 条目（避免重复）
  3. 调用 LLM 分析，生成优化建议 JSON
  4. 存回向量库 category="insight"
  5. 标记被总结的 experience
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_SUMMARY_INTERVAL = 86400     # 24 小时
_EXPERIENCE_THRESHOLD = 10     # 新积累多少条未总结经验触发
_EVOLUTION_PREFIX = "ev_"      # 元数据键前缀


class SelfEvolutionEngine:
    """自我进化引擎"""

    def __init__(self):
        self._last_run: Dict[str, float] = {}  # user_id → 上次总结时间戳
        self._vm = None

    @property
    def vm(self):
        if self._vm is None:
            try:
                from .vector_memory import VectorMemoryStore
                self._vm = VectorMemoryStore()
            except Exception as e:
                logger.debug(f"SelfEvolution: VectorMemory 不可用: {e}")
                self._vm = False
        return self._vm if self._vm else None

    async def check_and_evolve(self, user_id: str, new_experience_count: int = 1) -> None:
        """检查是否满足触发条件，满足则异步执行"""
        if not self.vm:
            return

        now = time.time()
        last = self._last_run.get(user_id, 0)
        time_elapsed = now - last

        # 条件：经验积累够多 或 超过一天没跑
        if new_experience_count < _EXPERIENCE_THRESHOLD and time_elapsed < _SUMMARY_INTERVAL:
            return

        logger.info(f"🧬 自我进化触发: user={user_id}, 距上次={time_elapsed:.0f}s")
        asyncio.ensure_future(self._run_evolution(user_id))

    async def _run_evolution(self, user_id: str) -> None:
        """执行一轮自我进化总结"""
        if not self.vm:
            return

        # 1. 读取未总结的经验
        unsummarized = self.vm.search_memories(
            query="任务 经验 策略 总结 搜索 代码 分析 优化 执行 处理",
            user_id=user_id,
            top_k=50,
        )
        pending = [
            m for m in unsummarized
            if m.get("metadata", {}).get("category") == "experience"
            and m.get("metadata", {}).get(_EVOLUTION_PREFIX + "summarized") != "true"
        ]
        if not pending:
            logger.debug(f"自我进化: user={user_id} 无未总结经验")
            self._last_run[user_id] = time.time()
            return

        # 2. 读取已有 insight（避免重复）
        existing = self.vm.search_memories(
            query="优化建议",
            user_id=user_id,
            top_k=20,
        )
        existing_insights = [
            m.get("content", "")[:100] for m in existing
            if m.get("metadata", {}).get("category") == "insight"
        ]

        # 3. 调用 LLM 分析
        insights = await self._llm_analyze_experiences(pending, existing_insights)
        if not insights:
            logger.debug(f"自我进化: LLM 未返回有效洞察")
            self._last_run[user_id] = time.time()
            return

        # 4. 写入 insight
        for ins in insights:
            try:
                self.vm.add_memory(
                    user_id=user_id,
                    content=ins.get("recommendation", str(ins)),
                    category="insight",
                    metadata={
                        "from": "self_evolution",
                        "type": ins.get("type", "behavior"),
                        "condition": ins.get("condition", ""),
                        _EVOLUTION_PREFIX + "timestamp": time.time(),
                    },
                )
            except Exception as e:
                logger.debug(f"写入 insight 失败: {e}")

        # 5. 标记经验已总结（直接更新元数据，安全无丢失）
        for m in pending:
            mid = m.get("id")
            if mid:
                try:
                    self.vm.update_metadata(
                        mid,
                        {_EVOLUTION_PREFIX + "summarized": "true"},
                    )
                except Exception:
                    logger.debug(f"标记经验已总结失败: id={mid}")

        self._last_run[user_id] = time.time()
        logger.info(f"🧬 自我进化完成: user={user_id}, {len(pending)}条经验→{len(insights)}条洞察")

    async def _llm_analyze_experiences(
        self, experiences: List[Dict], existing: List[str]
    ) -> List[Dict]:
        """调用 LLM 分析经验生成洞察"""
        exp_lines = [
            f"{i+1}. {m['content'][:300]}"
            for i, m in enumerate(experiences[:20])
        ]
        if not exp_lines:
            return []

        existing_str = "\n".join(f"- {e}" for e in existing[-5:]) if existing else "无"

        prompt = (
            "你是 V1 Agent 的自我进化引擎。分析以下最近积累的任务经验，"
            "提炼出可执行的优化建议，用于改进 V1 任务拆解和 Worker 分配的策略。\n\n"
            "【已有洞察】（避免重复）\n"
            f"{existing_str}\n\n"
            "【未总结经验】\n"
            + "\n".join(exp_lines) +
            "\n\n请输出 JSON 数组，每项格式：\n"
            '{"type": "behavior|pattern|avoid", '
            '"condition": "什么情况下适用", '
            '"recommendation": "具体怎么做"}'
        )

        try:
            from ..engine.llm_backend import get_llm_router
            router = get_llm_router()
            if not router:
                return []
            resp = await asyncio.wait_for(
                router.simple_chat(
                    user_message=prompt,
                    system_prompt="你是一个精炼的进化引擎，输出 JSON 数组。",
                    temperature=0.3,
                ),
                timeout=30,
            )
            if not resp:
                return []
            text = resp.strip() if isinstance(resp, str) else str(resp).strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed[:5]  # 最多 5 条
            if isinstance(parsed, dict) and "optimizations" in parsed:
                return parsed["optimizations"][:5]
            return []
        except asyncio.TimeoutError:
            logger.debug("自我进化: LLM 超时")
        except json.JSONDecodeError:
            logger.debug("自我进化: LLM 返回非 JSON")
        except Exception as e:
            logger.debug(f"自我进化: LLM 调用失败: {e}")
        return []


# 全局单例
_engine: Optional[SelfEvolutionEngine] = None


def get_evolution_engine() -> SelfEvolutionEngine:
    global _engine
    if _engine is None:
        _engine = SelfEvolutionEngine()
    return _engine
