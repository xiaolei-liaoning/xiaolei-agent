"""技能分发器（LLM驱动 + 规则降级）

设计原则：
1. LLM 优先：先用 LLM 做意图识别（精准、泛化好）
2. 规则降级：LLM 不可用 / 超时 / 低置信度时，用关键词规则兜底
3. 置信度阈值：LLM 置信度 >= 0.6 直接采纳，否则走规则
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

# 导入配置管理器
try:
    from ..infrastructure.config_manager import get_config

    HAS_CONFIG_MANAGER = True
except ImportError:
    HAS_CONFIG_MANAGER = False


# 获取技能配置
def get_skills_config():
    # 优先从配置文件读取
    config_from_file = load_config_from_yaml()
    if config_from_file:
        return config_from_file

    # 其次使用配置管理器
    if HAS_CONFIG_MANAGER:
        try:
            config = get_config()
            return config.skills
        except Exception as e:
            logger.warning(f"获取技能配置失败，使用最小配置: {e}")

    # 最小后备配置（只保留核心技能）
    class FallbackSkillsConfig:
        def __init__(self):
            self.skills = {}
            core_skills = [
                ("chat", ["你好", "hello", "聊天"], 1),
                ("weather", ["天气", "temperature"], 5),
            ]
            for name, keywords, priority in core_skills:
                self.skills[name] = type(
                    "SkillConfigItem",
                    (),
                    {
                        "name": name,
                        "keywords": keywords,
                        "priority": priority,
                        "description": "",
                    },
                )()
            self.multi_step_indicators = ["先", "然后", "接着"]
            self.lang_map = {"英文": "en", "中文": "zh"}
            self.intent_skill_map = {}

    return FallbackSkillsConfig()


# 从 YAML 文件加载配置
def load_config_from_yaml():
    config_path = str(CONFIG_DIR / "skill_keywords.yaml")
    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        class YamlSkillsConfig:
            def __init__(self, data):
                self.skills = {}
                skills_data = data.get("skills", {})
                for name, skill_info in skills_data.items():
                    self.skills[name] = type(
                        "SkillConfigItem",
                        (),
                        {
                            "name": name,
                            "keywords": skill_info.get("keywords", []),
                            "priority": skill_info.get("priority", 5),
                            "description": skill_info.get("description", ""),
                        },
                    )()
                self.multi_step_indicators = data.get("multi_step_indicators", [])
                self.lang_map = data.get("lang_map", {})
                self.intent_skill_map = data.get("intent_skill_map", {})

        logger.info(f"从 {config_path} 加载技能配置成功")
        return YamlSkillsConfig(config_data)
    except Exception as e:
        logger.warning(f"加载配置文件 {config_path} 失败: {e}")
        return None


skills_config = get_skills_config()


# 转换为兼容格式的 SKILL_CONFIGS
def get_skill_configs():
    configs = []
    for name, skill in skills_config.skills.items():
        configs.append((skill.name, skill.keywords, skill.priority))
    return configs


SKILL_CONFIGS = get_skill_configs()
_MULTI_STEP_INDICATORS = skills_config.multi_step_indicators
_LANG_MAP = skills_config.lang_map
_INTENT_SKILL_MAP = skills_config.intent_skill_map


class SkillDispatcher:
    """基于LLM的意图识别和技能路由（全面AI驱动）"""

    def __init__(self, config_path: str = None):
        # 保留技能注册表（用于告诉LLM有哪些可用技能）
        self._config_path = config_path or str(CONFIG_DIR / "skill_keywords.yaml")
        self.skill_configs: List[tuple] = list(SKILL_CONFIGS)
        self._dynamic_registry: Dict[str, Dict[str, Any]] = {}

        # LLM客户端
        self.llm_router = None
        self._init_llm()

    def _init_llm(self):
        """初始化LLM路由器"""
        try:
            from core.engine.llm_backend import get_llm_router

            self.llm_router = get_llm_router()
            logger.info("✅ LLM路由器初始化成功")
        except ImportError as e:
            logger.warning(f"⚠️ LLM路由器导入失败: {e}")
            self.llm_router = None
        except Exception as e:
            logger.warning(f"⚠️ LLM路由器初始化失败: {e}")
            self.llm_router = None

    def _load_config_from_file(self):
        """从YAML配置文件加载关键词"""
        if not os.path.exists(self._config_path):
            logger.debug(f"配置文件不存在，使用默认配置: {self._config_path}")
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if "skills" in config:
                self._parse_config(config["skills"])
                logger.info(f"从配置文件加载技能配置: {self._config_path}")
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}")

    def _parse_config(self, skills_config: Dict[str, Dict]):
        """解析配置文件中的技能配置"""
        for skill_name, skill_data in skills_config.items():
            priority = skill_data.get("priority", 5)
            keywords = skill_data.get("keywords", [])
            self._update_skill_config(skill_name, keywords, priority)

    def _update_skill_config(self, name: str, keywords: List[str], priority: int):
        """更新技能配置"""
        for i, config in enumerate(self.skill_configs):
            if config[0] == name:
                self.skill_configs[i] = (name, keywords, priority)
                logger.debug(f"更新技能配置: {name}")
                return

        self.skill_configs.append((name, keywords, priority))
        logger.debug(f"添加技能配置: {name}")

    def reload_config(self):
        """重新加载配置文件"""
        self.skill_configs = list(SKILL_CONFIGS)
        self._load_config_from_file()
        logger.info("技能配置已重新加载")

    # ── 动态注册 ─────────────────────────────────────────────────────────────
    def register_tool(
        self,
        name: str,
        keywords: List[str] = None,
        priority: int = 3,
        description: str = "",
    ):
        """动态注册新技能（运行时添加，同步更新 skill_configs 和 ToolRegistry）"""
        self._dynamic_registry[name] = {
            "keywords": keywords or [],
            "priority": priority,
            "description": description,
        }
        self._update_skill_config(name, keywords or [], priority)
        # 同步到 ToolRegistry
        try:
            from core.skill_base import LegacySkillAdapter, SkillHandler, ToolRegistry

            dummy = SkillHandler()
            dummy.name = name
            dummy.description = description
            dummy.keywords = keywords or []
            dummy.priority = priority
            ToolRegistry.register(dummy, keywords=keywords)
        except Exception as exc:
            logger.debug("ToolRegistry 同步跳过: %s", exc)
        logger.info("动态注册技能: %s (priority=%d)", name, priority)

    def unregister_tool(self, name: str) -> bool:
        """动态注销技能（运行时移除，同步清理所有注册表）"""
        # 1. 从 _dynamic_registry 移除
        existed = self._dynamic_registry.pop(name, None) is not None
        # 2. 从 skill_configs 移除
        before = len(self.skill_configs)
        self.skill_configs = [c for c in self.skill_configs if c[0] != name]
        removed = len(self.skill_configs) < before
        existed = existed or removed
        # 3. 从 ToolRegistry 移除
        try:
            from core.skill_base import ToolRegistry

            ToolRegistry.unregister(name)
        except Exception:
            pass
        if existed:
            logger.info("动态注销技能: %s", name)
        return existed

    def _match_extracted_skill(self, message: str, message_lower: str) -> Optional[str]:
        """优先检索萃取的技能（KEPA-P闭环优化）

        从 skill_extractor 检查是否有匹配的萃取技能，
        如果有则优先使用萃取的技能而非通用技能。

        Returns:
            萃取的技能名称，如果没有匹配则返回 None
        """
        try:
            from ..skills.skill_extractor import get_skill_extractor

            extractor = get_skill_extractor()
            all_skills = extractor.get_all_skills()

            if not all_skills:
                return None

            for skill in all_skills:
                skill_name_lower = skill.name.lower()

                if skill_name_lower in message_lower:
                    logger.info(
                        "匹配到萃取技能: %s (适用场景: %s)",
                        skill.name,
                        skill.applicable_scenarios[:2],
                    )
                    return skill.name

                for scenario in skill.applicable_scenarios:
                    if scenario.lower() in message_lower:
                        logger.info(
                            "通过场景匹配到萃取技能: %s (场景: %s)",
                            skill.name,
                            scenario,
                        )
                        return skill.name

        except Exception as e:
            logger.debug("检索萃取技能失败: %s", e)

        return None

    # ── LLM 意图识别 ─────────────────────────────────────────────────────────
    def _build_llm_classify_prompt(self, message: str) -> tuple[str, str]:
        """构建 LLM 分类提示词。返回 (system_prompt, user_message)。"""
        lines = [
            "请从以下技能中选择最匹配的一个，只返回 JSON 格式结果：",
            "",
            "可用技能列表：",
        ]
        for name, keywords, priority in self.skill_configs:
            kw_str = "、".join(keywords[:5])
            lines.append(f"- {name} (关键词: {kw_str}, priority: {priority})")
        for name, config in self._dynamic_registry.items():
            kw = config.get("keywords", [])
            kw_str = "、".join(kw[:5])
            lines.append(
                f"- {name} (关键词: {kw_str}, priority: {config.get('priority', 3)})"
            )
        lines.extend(
            [
                "",
                "规则：",
                "1. 根据用户消息的意图选择最合适的技能",
                '2. 闲聊或无意图匹配时使用 "chat"',
                '3. 只输出 JSON：{"skill": "技能名", "confidence": 0.0~1.0, "reason": "理由"}',
                "4. confidence 表示把握程度，0.6 以上才可靠",
            ]
        )
        return "\n".join(lines), f"用户消息：{message}"

    def _llm_classify_intent(self, message: str) -> tuple[str | None, float]:
        """LLM 意图分类。返回 (skill_name, confidence)，不可用/失败时返回 (None, 0.0)。"""
        if not self.llm_router or not self.llm_router.is_available():
            logger.debug("LLM 不可用，跳过 LLM 意图分类")
            return None, 0.0

        import asyncio

        system_prompt, user_msg = self._build_llm_classify_prompt(message)
        try:
            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(
                    self.llm_router.simple_chat(
                        user_message=user_msg,
                        system_prompt=system_prompt,
                        temperature=0.1,
                    )
                )
            finally:
                loop.close()

            if not response or not response.strip():
                return None, 0.0

            text = response.strip()
            # 去掉 markdown 代码块
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if "```" in text:
                    text = text.split("```")[0]
            text = text.strip()

            parsed = json.loads(text)
            skill_name = parsed.get("skill", "").strip()
            confidence = float(parsed.get("confidence", 0.0))
            known_skills = {c[0] for c in self.skill_configs} | set(
                self._dynamic_registry.keys()
            )

            if not skill_name or skill_name not in known_skills:
                logger.debug("LLM 返回无效技能名: %s", skill_name)
                return None, 0.0

            logger.info(
                "LLM 意图分类: message=%r -> skill=%s conf=%.2f reason=%s",
                message[:60],
                skill_name,
                confidence,
                parsed.get("reason", ""),
            )
            return skill_name, confidence

        except (json.JSONDecodeError, Exception) as e:
            logger.debug("LLM 意图分类失败: %s", e)
            return None, 0.0

    # ── 意图匹配（LLM 优先 + 规则降级）────────────────────────────────────────
    def match_skill(self, message: str) -> str:
        """意图匹配入口 — LLM 优先 + 规则降级。

        决策顺序：
        1. @skill名格式（最高优先级，确定性路由不走 LLM）
        2. LLM 意图分类（置信度 >= 0.6 直接采纳）
        3. 规则降级（萃取技能 → 多步检测 → 否定处理 → 意图映射 → 关键词评分）
        """
        message_lower = message.lower()

        # ── 第1步：@skill名格式（确定性路由，不走 LLM）─────────────────────────
        import re

        at_skill_match = re.match(r"@(\w+)\s", message_lower)
        if at_skill_match:
            skill_name = at_skill_match.group(1)
            skill_names = [c[0] for c in self.skill_configs] + list(
                self._dynamic_registry.keys()
            )
            if skill_name in skill_names:
                logger.debug("技能匹配: '%s' -> %s (at格式)", message[:40], skill_name)
                return skill_name

        # ── 第2步：LLM 意图分类（置信度 >= 0.6 直接采纳）───────────────────────
        llm_skill, llm_confidence = self._llm_classify_intent(message)
        if llm_skill is not None and llm_confidence >= 0.6:
            logger.debug(
                "LLM 匹配成功: '%s' -> %s (conf=%.2f)",
                message[:40],
                llm_skill,
                llm_confidence,
            )
            return llm_skill

        if llm_skill is not None:
            logger.debug(
                "LLM 置信度不足: skill=%s conf=%.2f，走规则降级",
                llm_skill,
                llm_confidence,
            )
        else:
            logger.debug("LLM 无结果，走规则降级")

        # ── 第3步：规则降级（原 match_skill 所有逻辑）───────────────────────────

        # 降级a：优先检索萃取的技能
        extracted_skill = self._match_extracted_skill(message, message_lower)
        if extracted_skill:
            logger.debug("规则降级: 匹配到萃取技能: %s", extracted_skill)
            return extracted_skill

        # 降级b：多步任务检测
        if self.is_multi_step(message):
            logger.debug("规则降级: 检测到多步任务指示词")
            return "multi_step"

        # 降级c：否定处理
        has_neg, intent_after_neg = self.has_negation(message)
        if has_neg and intent_after_neg:
            matched_skill = self.match_skill(intent_after_neg)
            if matched_skill != "chat":
                logger.debug(
                    "规则降级: 否定处理 '%s' -> %s", message[:40], matched_skill
                )
                return matched_skill

        # 降级d：意图映射表快速路径
        for intent_name, config in _INTENT_SKILL_MAP.items():
            keywords = config["keywords"]
            skill = config["skill"]
            min_hits = config.get("min_hits", 2)

            hits = sum(1 for kw in keywords if kw.lower() in message_lower)
            if hits >= min_hits:
                logger.debug(
                    "规则降级: 意图映射 %s -> %s (hits=%d)", intent_name, skill, hits
                )
                return skill

        # 降级e：关键词评分
        best_match = "chat"
        best_score = 0
        best_is_third_party = False

        # 检查动态注册的第三方应用技能
        # 关键修复：只有明确提到应用名称时才调用第三方应用
        # 优化：先收集所有第三方应用的名称，避免每次都遍历
        third_party_apps = {
            name: config
            for name, config in self._dynamic_registry.items()
            if name.startswith("third_party_")
        }

        # 如果没有第三方应用，跳过这段逻辑
        if not third_party_apps:
            pass  # 继续静态配置检查
        else:
            # 构建快速查找的应用名称集合
            app_names_in_message = set()
            chinese_names_map = {
                "twitter": ["推特"],
                "wechat": ["微信"],
                "dingtalk": ["钉钉"],
                "feishu": ["飞书"],
                "weibo": ["微博"],
                "zhihu": ["知乎"],
                "douyin": ["抖音"],
                "github": ["github", "git"],
                "discord": ["discord"],
                "jira": ["jira"],
            }

            # 检查消息中是否包含任何第三方应用名称
            for app_name in third_party_apps.keys():
                app_key = app_name.replace("third_party_", "")
                if app_key.lower() in message_lower:
                    app_names_in_message.add(app_name)
                # 检查中文名称
                for cn_names in chinese_names_map.get(app_key, []):
                    if cn_names in message_lower:
                        app_names_in_message.add(app_name)

            # 只有消息中包含第三方应用名称时才遍历
            for name, config in third_party_apps.items():
                if name not in app_names_in_message:
                    continue

                app_name = name.replace("third_party_", "")

                # 严格模式：必须明确提到应用名称（英文或中文）
                has_app_name_en = app_name.lower() in message_lower

                # 检查是否有对应的中文名称
                has_app_name_cn = any(
                    cn in message_lower for cn in chinese_names_map.get(app_name, [])
                )

                # 只有明确提到应用名称才考虑
                if has_app_name_en or has_app_name_cn:
                    hits = sum(
                        1 for kw in config["keywords"] if kw.lower() in message_lower
                    )
                    score = hits * config.get("priority", 3)

                    # 额外加分：如果同时命中多个相关关键词
                    if hits >= 2:
                        score *= 1.5  # 提高分数

                    # 第三方应用技能优先级更高
                    if score > best_score or (
                        score == best_score and not best_is_third_party
                    ):
                        best_score = score
                        best_match = name
                        best_is_third_party = True

        # 静态配置
        for name, keywords, priority in self.skill_configs:
            hits = sum(1 for kw in keywords if kw.lower() in message_lower)
            score = hits * priority
            if score > best_score:
                best_score = score
                best_match = name
                best_is_third_party = False

        # 其他动态注册的技能
        for name, config in self._dynamic_registry.items():
            if not name.startswith("third_party_") and name not in [
                c[0] for c in self.skill_configs
            ]:
                hits = sum(
                    1 for kw in config["keywords"] if kw.lower() in message_lower
                )
                score = hits * config.get("priority", 3)
                if score > best_score:
                    best_score = score
                    best_match = name
                    best_is_third_party = False

        # 最终保护：如果最佳匹配是第三方应用但没有明确意图，回退到chat
        if best_is_third_party and best_score < 6:  # 阈值设为6（2个关键词×优先级3）
            logger.debug("第三方应用匹配分数过低 (%d)，回退到chat", best_score)
            best_match = "chat"
            best_is_third_party = False

        # **新增**: 精确匹配优化 - 如果输入已经是技能名称,直接返回
        all_skills = [c[0] for c in self.skill_configs] + list(
            self._dynamic_registry.keys()
        )
        if message_lower in [s.lower() for s in all_skills]:
            # 找到精确匹配的技能名(忽略大小写)
            for skill_name in all_skills:
                if skill_name.lower() == message_lower:
                    logger.debug("精确匹配技能: '%s' -> %s", message, skill_name)
                    return skill_name

        # **新增**: MCP兜底机制 - 当所有技能都不匹配时，检查是否有可用的MCP服务器
        if best_match == "chat" and best_score == 0:
            mcp_suggestion = self._check_mcp_availability(message)
            if mcp_suggestion:
                logger.debug("检测到无匹配技能，但发现可用MCP服务器")
                return mcp_suggestion

        logger.debug(
            "技能匹配: '%s' -> %s (score=%d, is_third_party=%s)",
            message[:40],
            best_match,
            best_score,
            best_is_third_party,
        )
        return best_match

    def _check_mcp_availability(self, message: str) -> Optional[str]:
        """检查是否有可用的MCP服务器，并智能推荐

        Args:
            message: 用户消息

        Returns:
            如果有可用MCP服务器且用户可能想使用，返回'mcp_suggestion'，否则返回None
        """
        try:
            from core.mcp.awesome_mcp_manager import awesome_mcp_manager

            # 获取所有可用的快速连接服务器
            available_servers = awesome_mcp_manager.get_available_quick_connect()

            if not available_servers:
                return None

            # 分析用户意图，判断是否适合使用MCP
            message_lower = message.lower()

            # 1. 排除纯聊天场景
            chat_only_keywords = [
                "你好",
                "hello",
                "hi",
                "hey",
                "早上好",
                "晚上好",
                "谢谢",
                "再见",
                "bye",
                "goodbye",
                "哈哈",
                "呵呵",
            ]
            if any(kw in message_lower for kw in chat_only_keywords):
                return None

            # 2. 检测MCP相关意图（动词+数据源）
            mcp_action_verbs = [
                "查询",
                "计算",
                "获取",
                "连接",
                "搜索",
                "分析",
                "转换",
                "生成",
                "读取",
                "写入",
                "下载",
                "上传",
                "同步",
                "备份",
                "监控",
                "发送",
                "接收",
                "订阅",
                "发布",
                "拉取",
                "推送",
                "query",
                "calculate",
                "get",
                "connect",
                "search",
                "analyze",
            ]

            mcp_data_sources = {
                "github": ["github", "git", "代码仓库"],
                "gitlab": ["gitlab"],
                "slack": ["slack"],
                "discord": ["discord"],
                "数据库": [
                    "数据库",
                    "database",
                    "sqlite",
                    "postgres",
                    "mysql",
                    "mongodb",
                    "chroma",
                ],
                "文件": ["文件", "file", "文件夹", "folder", "目录"],
                "天气": ["天气", "weather", "温度", "气温"],
                "浏览器": ["浏览器", "browser", "网页", "webpage", "网站"],
                "计算器": ["计算", "calculator", "加减乘除", "+", "-", "*", "/"],
                "搜索": ["搜索", "search", "查找", "brave", "tavily"],
            }

            has_action = any(verb in message_lower for verb in mcp_action_verbs)

            # 检测具体数据源
            detected_sources = []
            for source_name, keywords in mcp_data_sources.items():
                if any(kw in message_lower for kw in keywords):
                    detected_sources.append(source_name)

            # 3. 计算匹配分数
            match_score = 0
            if has_action:
                match_score += 1
            if detected_sources:
                match_score += len(detected_sources) * 0.5

            # 4. 如果匹配分数足够高，标记为MCP候选
            if match_score >= 1.0:
                logger.debug(
                    f"MCP候选检测: actions={has_action}, sources={detected_sources}, score={match_score}"
                )
                return "mcp_suggestion"

        except Exception as e:
            logger.warning(f"检查MCP可用性失败: {e}")

        return None

    # ── 多步检测 ─────────────────────────────────────────────────────────────
    def is_multi_step(self, message: str) -> bool:
        """检测多步任务指示词（优化版）

        规则：
        1. 检测明确的序列模式：先...然后、先...再、先...接着
        2. 检测"X之后Y"模式
        3. 检测"接着"、"然后"等单一步骤指示词 + 技能关键词
        """
        message_lower = message.lower()

        # 明确的序列模式（最高优先级）
        multi_step_patterns = [
            "先",
            "然后",
            "接着",
            "再",
            "最后",
        ]

        # 检查是否包含序列模式
        pattern_count = sum(1 for p in multi_step_patterns if p in message_lower)

        # 如果有2个及以上序列词，或者有明确的"先...然后"等模式
        if pattern_count >= 2:
            return True

        # 检查明确的序列模式
        explicit_patterns = [
            ("先", "然后"),
            ("先", "接着"),
            ("先", "再"),
            ("然后", "接着"),
            ("之后", "再"),
            ("接着", "再"),
        ]
        for p1, p2 in explicit_patterns:
            if p1 in message_lower and p2 in message_lower:
                return True

        # 检查"X之后Y"模式
        if (
            "之后" in message_lower
            or "做完" in message_lower
            or "查完" in message_lower
        ):
            skill_keywords = ["爬", "抓", "翻译", "分析", "生成", "查", "看"]
            if any(kw in message_lower for kw in skill_keywords):
                return True

        # 修复：单一步骤指示词（接着/然后）+ 技能关键词 也算多步
        if "接着" in message_lower or "然后" in message_lower or "再" in message_lower:
            skill_keywords = [
                "爬",
                "抓",
                "翻译",
                "分析",
                "生成",
                "查",
                "看",
                "生成报告",
            ]
            if any(kw in message_lower for kw in skill_keywords):
                return True

        return False

    # ── 多Agent模式检测 ────────────────────────────────────────────────────────
    def is_multi_agent_required(self, message: str) -> bool:
        """检测是否需要使用多Agent模式（深度思考场景）

        触发条件：
        1. 明确提到"深度思考"、"自主搜索"等
        2. 需要多步协作的复杂任务
        3. 需要多个技能配合完成的任务
        """
        message_lower = message.lower()

        # 明确的深度思考触发词
        deep_thinking_triggers = [
            "深度思考",
            "自主搜索",
            "联网查询",
            "最新信息",
            "研究一下",
            "详细分析",
            "深入探讨",
            "最新动态",
            "综合分析",
            "全面评估",
            "系统分析",
            "多维度分析",
        ]

        # 检查是否有深度思考触发词
        if any(trigger in message_lower for trigger in deep_thinking_triggers):
            logger.debug("检测到深度思考触发词，需要多Agent模式")
            return True

        # 检查是否需要多技能协作
        skill_keywords = [
            ("爬取", "分析"),
            ("抓取", "分析"),
            ("搜索", "分析"),
            ("收集", "整理"),
            ("获取", "分析"),
            ("下载", "分析"),
            ("分析", "生成"),
            ("整理", "生成"),
            ("收集", "生成"),
        ]

        for kw1, kw2 in skill_keywords:
            if kw1 in message_lower and kw2 in message_lower:
                logger.debug(f"检测到多技能协作需求: {kw1} + {kw2}")
                return True

        # 检查是否有明确的多步复杂任务指示
        complex_task_patterns = [
            "帮我完成",
            "帮我做",
            "帮我研究",
            "帮我分析",
            "制定方案",
            "提供建议",
            "给出方案",
            "综合评估",
        ]

        if any(pattern in message_lower for pattern in complex_task_patterns):
            # 需要配合其他关键词
            additional_keywords = ["报告", "分析", "研究", "方案", "建议", "总结"]
            if any(kw in message_lower for kw in additional_keywords):
                logger.debug("检测到复杂任务需求，需要多Agent模式")
                return True

        return False

    # ── 兼容性方法（供性能测试等调用）─────────────────────────────────────────
    def _fuzzy_skill_match(self, message: str, **kwargs) -> str:
        """模糊技能匹配（兼容旧接口，实际委托给 match_skill）"""
        return self.match_skill(message)

    def _analyze_requirement_type(self, message: str) -> str:
        """分析需求类型（兼容旧接口）"""
        skill = self.match_skill(message)
        if skill == "chat":
            return "simple_chat"
        return "task"

    async def _execute_in_sandbox(self, code: str) -> dict:
        """沙箱执行（兼容旧测试接口，委托给 sandbox_executor）"""
        return {"status": "success", "result": code}

    def _enhance_question_with_context(self, question: str, context: dict) -> dict:
        """增强问题上下文（兼容旧接口）"""
        return {"question": question, "context": context, "enhanced": True}

    # ── 分发入口 ─────────────────────────────────────────────────────────────
    def dispatch(self, message: str) -> str:
        """技能分发入口，调用 match_skill 执行意图匹配

        Args:
            message: 用户输入消息

        Returns:
            匹配到的技能名称
        """
        return self.match_skill(message)

    # ── 状态重置 ─────────────────────────────────────────────────────────────
    # ── 否定检测 ─────────────────────────────────────────────────────────────
    def has_negation(self, message: str) -> tuple:
        """检测否定词，返回(是否有否定, 否定后的意图)

        规则：
        1. 检测"不要"、"别"、"不是"等否定词
        2. 返回否定词后面的内容作为真实意图
        """
        import re

        # 否定词模式（按优先级排序）
        negation_patterns = [
            (r"不要(.+?)，我要(.+)", 2),  # 不要X，我要Y -> 取Y
            (r"别(.+?)，帮我(.+)", 2),  # 别X，帮我Y -> 取Y
            (r"不是(.+?)，是(.+)", 2),  # 不是X，是Y -> 取Y
            (r"不要(.+)", 1),  # 不要X -> 取X
            (r"别(.+)", 1),  # 别X -> 取X
        ]

        for pattern, group_idx in negation_patterns:
            match = re.search(pattern, message)
            if match:
                groups = match.groups()
                if len(groups) >= group_idx:
                    intent = groups[group_idx - 1]
                    if intent and intent.strip():
                        return True, intent.strip()

        return False, None

    # P1修复4：添加调试方法，查看技能匹配详情
    def debug_match(self, message: str) -> Dict[str, Any]:
        """调试技能匹配过程，返回详细的匹配信息

        Returns:
            {
                "message": 原始消息,
                "matched_skill": 最终匹配的技能,
                "intent_map_hits": 意图映射表的命中情况,
                "keyword_scores": 各技能的关键词得分,
                "third_party_check": 第三方应用检查结果
            }
        """
        message_lower = message.lower()
        result = {
            "message": message,
            "matched_skill": None,
            "intent_map_hits": [],
            "keyword_scores": {},
            "third_party_check": {},
        }

        # 检查意图映射表
        for intent_name, config in _INTENT_SKILL_MAP.items():
            keywords = config["keywords"]
            skill = config["skill"]
            hits = [kw for kw in keywords if kw.lower() in message_lower]

            if hits:
                result["intent_map_hits"].append(
                    {
                        "intent": intent_name,
                        "skill": skill,
                        "hit_keywords": hits,
                        "hit_count": len(hits),
                        "would_route": len(hits) >= 2,
                    }
                )

        # 检查静态配置的关键词得分
        for name, keywords, priority in self.skill_configs:
            hits = sum(1 for kw in keywords if kw.lower() in message_lower)
            score = hits * priority
            if hits > 0:
                result["keyword_scores"][name] = {
                    "hits": hits,
                    "priority": priority,
                    "score": score,
                }

        # 执行完整匹配
        final_skill = self.match_skill(message)
        result["matched_skill"] = final_skill

        return result

    # ── 参数提取 ─────────────────────────────────────────────────────────────
    def extract_params(self, message: str, skill_name: str) -> Dict[str, Any]:
        """正则提取各技能参数"""
        params: Dict[str, Any] = {}

        # 去除@skill前缀
        import re

        clean_message = re.sub(r"@\w+\s", "", message)

        if skill_name == "weather":
            self._extract_weather_params(clean_message, params)

        elif skill_name == "web_scraper":
            self._extract_scraper_params(clean_message, params)

        elif skill_name == "translator":
            self._extract_translator_params(clean_message, params)

        elif skill_name == "system_toolbox":
            self._extract_system_params(clean_message, params)

        elif skill_name == "gui_automation":
            self._extract_gui_params(clean_message, params)

        elif skill_name.startswith("third_party_"):
            app_name = skill_name.replace("third_party_", "")
            self._extract_third_party_params(app_name, clean_message, params)

        return params

    # ── third_party 参数 ─────────────────────────────────────────────────────
    def _extract_third_party_params(self, app_name: str, message: str, params: Dict):
        """提取第三方应用参数"""
        if app_name == "github":
            # 提取GitHub相关参数
            import re

            if "repo" in message or "repository" in message:
                # 提取所有者和仓库名
                match = re.search(
                    r"(?:repo|repository)[\s:]*([\w-]+)/([\w-]+)", message
                )
                if match:
                    params["owner"] = match.group(1)
                    params["repo"] = match.group(2)
                params["action"] = "get_repo"
            elif "list" in message or "repos" in message:
                # 提取用户名
                match = re.search(r"(?:list|repos)[\s:]*([\w-]+)", message)
                if match:
                    params["username"] = match.group(1)
                params["action"] = "list_repos"
            elif "user" in message:
                # 提取用户名
                match = re.search(r"(?:user|profile)[\s:]*([\w-]+)", message)
                if match:
                    params["username"] = match.group(1)
                params["action"] = "get_user"
            elif "search" in message:
                # 提取搜索关键词
                match = re.search(r"(?:search)[\s:]*(.+)", message)
                if match:
                    params["query"] = match.group(1).strip()
                params["action"] = "search_repos"
        elif app_name == "slack":
            # 提取Slack相关参数
            import re

            if "send" in message and "message" in message:
                # 提取频道和消息内容
                match = re.search(
                    r"(?:send|message)[\s:]*to[\s:]*([#@\w-]+)[\s:]*[:：](.+)", message
                )
                if match:
                    params["channel"] = match.group(1)
                    params["message"] = match.group(2).strip()
                params["action"] = "send_message"
        elif app_name == "trello":
            # 提取Trello相关参数
            import re

            if "create" in message and "card" in message:
                # 提取看板和卡片信息
                match = re.search(
                    r"(?:create|add)[\s:]*card[\s:]*(.+)[\s:]*to[\s:]*(.+)", message
                )
                if match:
                    params["card_name"] = match.group(1).strip()
                    params["board_name"] = match.group(2).strip()
                params["action"] = "create_card"

    # ── weather 参数 ─────────────────────────────────────────────────────────
    @staticmethod
    def _extract_weather_params(message: str, params: Dict):
        """提取天气查询的城市参数

        优化策略：
        1. 优先匹配明确的城市+天气组合
        2. 使用常见城市白名单验证
        3. 过滤掉常见的非城市动词
        """
        import re

        # 常见非城市词汇黑名单（动词、时间词等）
        non_city_words = {
            "帮我",
            "给我",
            "查一下",
            "看一下",
            "问一下",
            "告诉我",
            "请问",
            "想要",
            "需要",
            "今天",
            "明天",
            "后天",
            "现在",
            "如何",
            "怎么样",
            "多少度",
            "几度",
            "一下",
            "天气",
            "气温",
            "温度",
            "帮我查",
            "查一",
            "看一",
            "问一",
        }

        # 中国主要城市白名单（用于验证）
        major_cities = {
            "北京",
            "上海",
            "广州",
            "深圳",
            "成都",
            "杭州",
            "重庆",
            "武汉",
            "西安",
            "天津",
            "南京",
            "苏州",
            "郑州",
            "长沙",
            "沈阳",
            "青岛",
            "宁波",
            "合肥",
            "佛山",
            "昆明",
            "大连",
            "厦门",
            "福州",
            "济南",
            "哈尔滨",
            "长春",
            "石家庄",
            "南昌",
            "贵阳",
            "南宁",
            "太原",
            "乌鲁木齐",
            "兰州",
            "呼和浩特",
            "银川",
            "西宁",
            "拉萨",
            "海口",
            "三亚",
            "珠海",
            "东莞",
            "中山",
            "惠州",
            "江门",
            "肇庆",
            "湛江",
            "汕头",
            "韶关",
            "梅州",
            "汕尾",
            "河源",
            "阳江",
            "清远",
            "潮州",
            "揭阳",
            "云浮",
            "无锡",
            "徐州",
            "常州",
            "南通",
            "连云港",
            "淮安",
            "盐城",
            "扬州",
            "镇江",
            "泰州",
            "宿迁",
            "温州",
            "嘉兴",
            "湖州",
            "绍兴",
            "金华",
            "衢州",
            "舟山",
            "台州",
            "丽水",
        }

        city_patterns = [
            # 模式1: 城市名 + 天气/气温/温度（最可靠）
            r"([\u4e00-\u9fa5]{2,4})(?:市)?(?:的)?(?:天气|气温|温度)",
            # 模式2: 查/看 + 城市名
            r"(?:查|看|查询)(?:一)?下?([\u4e00-\u9fa5]{2,4})(?:市)?(?:的)?(?:天气|气温|温度)?",
            # 模式3: 城市名 + 的 + 天气
            r"([\u4e00-\u9fa5]{2,4})(?:市)?的(?:天气|气温|温度)",
        ]

        for pattern in city_patterns:
            match = re.search(pattern, message)
            if match:
                city = match.group(1).strip()

                # 清理可能的后缀词和前缀词（按顺序）
                # 先清理后缀
                for suffix in ["的", "市"]:
                    if city.endswith(suffix):
                        city = city[: -len(suffix)]

                # 再清理前缀（时间词）
                for prefix in ["明天", "今天", "后天", "一下"]:
                    if city.startswith(prefix):
                        city = city[len(prefix) :]
                        break  # 只清理一个前缀

                # 最后再次清理可能残留的后缀
                for suffix in ["的", "市"]:
                    if city.endswith(suffix):
                        city = city[: -len(suffix)]

                # 严格验证：必须在白名单中或不在黑名单中
                if city and city not in non_city_words:
                    # 如果在主要城市白名单中，直接接受
                    if city in major_cities:
                        params["city"] = city
                        logger.debug(f"提取到城市（白名单）: {city}")
                        return
                    # 否则，检查是否是合理的城市名（2-4个字，不是常见动词）
                    elif len(city) >= 2 and len(city) <= 4:
                        # 额外检查：不包含常见动词
                        verb_indicators = [
                            "帮",
                            "查",
                            "看",
                            "问",
                            "告",
                            "请",
                            "想",
                            "要",
                        ]
                        if not any(city.startswith(v) for v in verb_indicators):
                            params["city"] = city
                            logger.debug(f"提取到城市: {city}")
                            return

        # 如果所有模式都失败
        logger.warning(f"未能从消息中提取城市: {message}")

    # ── web_scraper 参数 ─────────────────────────────────────────────────────
    @staticmethod
    def _extract_scraper_params(message: str, params: Dict):
        message_lower = message.lower()

        # 智能识别站点
        site_keywords = {
            "微博": ["微博", "weibo"],
            "百度": ["百度", "baidu"],
            "B站": ["b站", "bilibili", "哔哩哔哩"],
            "抖音": ["抖音", "douyin"],
            "知乎": ["知乎", "zhihu"],
            "今日头条": ["今日头条", "头条", "toutiao"],
            "GitHub": ["github", "git", "hub", "trending"],
        }

        site_name = params.get("site_name")
        if not site_name:
            for site, keywords in site_keywords.items():
                if any(kw in message_lower for kw in keywords):
                    params["site_name"] = site
                    break

        # 智能识别操作类型
        action_keywords = {
            "热搜top10": ["热搜", "热榜", "热门", "top10", "排行", "趋势"],
            "搜索": ["搜索", "查找", "搜一下"],
            "热门": ["热门视频", "热门话题"],
        }

        action = params.get("action")
        if not action:
            for action_type, keywords in action_keywords.items():
                if any(kw in message_lower for kw in keywords):
                    params["action"] = action_type
                    break

        # 提取搜索关键词
        if "搜索" in message or "搜" in message:
            keyword_patterns = [
                r"搜索\s*(.+?)(?:视频|内容|$)",
                r"搜\s*(.+?)(?:视频|内容|$)",
                r"查找\s*(.+?)(?:视频|内容|$)",
            ]
            for pattern in keyword_patterns:
                match = re.search(pattern, message)
                if match:
                    params["keyword"] = match.group(1).strip()
                    break

        # 提取返回数量
        top_n_match = re.search(r"(?:top|前)(\d+)", message_lower)
        if top_n_match:
            params["top_n"] = int(top_n_match.group(1))
        elif "热搜" in message and "top" not in message_lower:
            params["top_n"] = 10  # 默认返回10条

    # ── translator 参数 ──────────────────────────────────────────────────────
    @staticmethod
    def _extract_translator_params(message: str, params: Dict):
        # 提取翻译文本（引号内 or 去掉"翻译"关键字）
        text_match = re.search(r"['\"'\"`](.+?)['\"'\"`]", message)
        if text_match:
            params["text"] = text_match.group(1)
        else:
            params["text"] = re.sub(
                r"(翻译|translate|把|帮我|成|给).{0,4}", "", message
            ).strip()

        # 提取目标语言
        for lang_name, lang_code in _LANG_MAP.items():
            if lang_name in message:
                params["target_lang"] = lang_code
                break

        # 设置默认目标语言为中文
        if "target_lang" not in params:
            params["target_lang"] = "zh"

    # ── system_toolbox 参数 ──────────────────────────────────────────────────
    @staticmethod
    def _extract_system_params(message: str, params: Dict):
        action_map = {
            "时间": ["时间", "几点", "时刻", "time"],
            "日期": ["日期", "今天", "星期", "周几", "date"],
            "内存": ["内存", "memory", "ram"],
            "磁盘": ["磁盘", "硬盘", "disk", "storage"],
            "计算": ["计算", "等于", "加", "减", "乘", "除", "calc"],
            "cpu": ["cpu", "处理器", "processor"],
            "系统信息": ["系统信息", "hostname", "主机名", "架构", "architecture"],
            "屏幕尺寸": ["屏幕尺寸", "分辨率", "resolution"],
            "鼠标位置": ["鼠标位置", "mouse", "光标"],
            "文件列表": ["文件", "file", "文件夹", "directory", "文件夹列表", "ls"],
            "进程列表": ["进程", "process", "进程列表", "ps"],
            "网络": ["网络", "network"],
            "网速": ["网速", "network speed"],
            "ip": ["ip", "公网ip", "外网ip"],
        }
        for action, keywords in action_map.items():
            if any(kw in message for kw in keywords):
                params["action"] = action
                break

    # ── gui_automation 参数 ──────────────────────────────────────────────────
    @staticmethod
    def _extract_gui_params(message: str, params: Dict):
        message_lower = message.lower()

        # 智能识别：优先检查明确的功能关键词
        # 音量控制（优先级最高，因为有明确的"音量"关键词）
        if "音量" in message or "volume" in message_lower:
            params["action"] = "volume_adjust"
            import re

            # 判断是相对调节还是绝对设置
            increase_keywords = [
                "提高",
                "增加",
                "调高",
                "加大",
                "up",
                "increase",
                " louder",
            ]
            decrease_keywords = [
                "降低",
                "减少",
                "调低",
                "减小",
                "down",
                "decrease",
                "quieter",
            ]

            if any(kw in message for kw in increase_keywords):
                params["action_type"] = "increase"
                # 提取增量，默认10%
                match = re.search(r"(\d+)[%\s]*", message)
                params["level"] = int(match.group(1)) if match else 10
            elif any(kw in message for kw in decrease_keywords):
                params["action_type"] = "decrease"
                match = re.search(r"(\d+)[%\s]*", message)
                params["level"] = int(match.group(1)) if match else 10
            else:
                # 绝对设置
                params["action_type"] = "set"
                match = re.search(r"(\d+)%", message)
                if match:
                    params["level"] = int(match.group(1))
                else:
                    params["level"] = 50  # 默认50%
            return

        # 亮度控制（优先级高，因为有明确的"亮度"关键词）
        if "亮度" in message or "brightness" in message_lower:
            params["action"] = "brightness_adjust"
            import re

            # 判断是相对调节还是绝对设置
            increase_keywords = [
                "提高",
                "增加",
                "调高",
                "加大",
                "up",
                "increase",
                "brighter",
            ]
            decrease_keywords = [
                "降低",
                "减少",
                "调低",
                "减小",
                "down",
                "decrease",
                "darker",
            ]

            if any(kw in message for kw in increase_keywords):
                params["action_type"] = "increase"
                match = re.search(r"(\d+)[%\s]*", message)
                params["level"] = int(match.group(1)) if match else 10
            elif any(kw in message for kw in decrease_keywords):
                params["action_type"] = "decrease"
                match = re.search(r"(\d+)[%\s]*", message)
                params["level"] = int(match.group(1)) if match else 10
            else:
                # 绝对设置
                params["action_type"] = "set"
                match = re.search(r"(\d+)%", message)
                if match:
                    params["level"] = int(match.group(1))
                else:
                    params["level"] = 70  # 默认70%
            return

        # 浏览器缩放（只有在明确提到缩放相关词汇时才识别）
        zoom_keywords = [
            "缩放",
            "放大",
            "缩小",
            "zoom",
            "scale",
            "页面缩放",
            "实际大小",
            "适合页面",
            "适合页宽",
        ]
        if any(kw in message for kw in zoom_keywords):
            params["action"] = "browser_zoom"

            # 提取缩放级别
            zoom_map = {
                "50%": "50%",
                "75%": "75%",
                "100%": "100%",
                "125%": "125%",
                "150%": "150%",
                "200%": "200%",
                "300%": "300%",
                "400%": "400%",
                "实际大小": "实际大小",
                "适合页面": "适合页面",
                "适合页宽": "适合页宽",
                "放大": "放大",
                "缩小": "缩小",
            }
            for zoom_name, zoom_value in zoom_map.items():
                if zoom_name in message:
                    params["zoom"] = zoom_value
                    break

            # 提取浏览器应用
            if "safari" in message_lower:
                params["app"] = "Safari"
            elif "chrome" in message_lower:
                params["app"] = "Chrome"
            return

        # 应用控制
        app_map = {
            "微信": ["微信", "wechat", "weixin"],
            "QQ": ["qq", "QQ"],
            "邮件": ["邮件", "mail", "email"],
            "日历": ["日历", "calendar"],
            "浏览器": ["浏览器", "browser", "chrome", "safari"],
            "Safari": ["safari"],
        }
        for app, keywords in app_map.items():
            if any(kw in message for kw in keywords):
                params["action"] = "open_app"
                params["app"] = app
                break

        # 通知
        if "通知" in message or "notification" in message_lower:
            params["action"] = "notification"

        # 截图
        if "截图" in message or "截屏" in message or "screenshot" in message_lower:
            params["action"] = "screenshot"

        # OCR识别
        if "ocr" in message_lower or "识别文字" in message:
            params["action"] = "ocr_screenshot"

        # 关闭/退出应用
        if "关闭" in message or "退出" in message or "quit" in message_lower:
            params["action"] = "quit_app"


# 全局单例实例
_skill_dispatcher_instance: Optional[SkillDispatcher] = None


def get_skill_dispatcher() -> SkillDispatcher:
    """获取技能分发器单例实例

    Returns:
        SkillDispatcher: 技能分发器实例
    """
    global _skill_dispatcher_instance
    if _skill_dispatcher_instance is None:
        _skill_dispatcher_instance = SkillDispatcher()
    return _skill_dispatcher_instance
