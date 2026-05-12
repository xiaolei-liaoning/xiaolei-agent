#!/usr/bin/env python3
"""持续学习模块 - 从经验中学习"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Experience:
    """经验记录"""

    def __init__(self, task: str, action: str, result: str, success: bool, feedback: str = ""):
        self.task = task
        self.action = action
        self.result = result
        self.success = success
        self.feedback = feedback
        self.timestamp = asyncio.get_event_loop().time()
        self.confidence = 0.0

    def to_dict(self) -> Dict:
        return {
            "task": self.task,
            "action": self.action,
            "result": self.result,
            "success": self.success,
            "feedback": self.feedback,
            "timestamp": self.timestamp,
            "confidence": self.confidence
        }


class ExperienceMemory:
    """经验记忆系统"""

    def __init__(self):
        self.positive_experiences: List[Experience] = []
        self.negative_experiences: List[Experience] = []
        self.max_memory_size = 1000
        self._load_from_disk()

    def add_experience(self, experience: Experience):
        """添加经验"""
        if experience.success:
            self.positive_experiences.append(experience)
        else:
            self.negative_experiences.append(experience)

        # 限制内存大小
        self._trim_memory()
        
        # 保存到磁盘
        self._save_to_disk()

    def _trim_memory(self):
        """修剪内存，保持在最大限制内"""
        # 按时间排序，保留最新的
        self.positive_experiences.sort(key=lambda x: x.timestamp, reverse=True)
        self.negative_experiences.sort(key=lambda x: x.timestamp, reverse=True)

        # 裁剪到最大大小
        self.positive_experiences = self.positive_experiences[:self.max_memory_size]
        self.negative_experiences = self.negative_experiences[:self.max_memory_size]

    def _save_to_disk(self):
        """保存经验到磁盘"""
        try:
            data = {
                "positive": [e.to_dict() for e in self.positive_experiences],
                "negative": [e.to_dict() for e in self.negative_experiences]
            }
            
            os.makedirs("data", exist_ok=True)
            with open("data/experiences.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("经验保存成功")
        except Exception as e:
            logger.error(f"保存经验失败: {e}")

    def _load_from_disk(self):
        """从磁盘加载经验"""
        try:
            with open("data/experiences.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                
                for exp_dict in data.get("positive", []):
                    exp = Experience(
                        task=exp_dict["task"],
                        action=exp_dict["action"],
                        result=exp_dict["result"],
                        success=True,
                        feedback=exp_dict.get("feedback", "")
                    )
                    exp.timestamp = exp_dict.get("timestamp", 0)
                    exp.confidence = exp_dict.get("confidence", 0.0)
                    self.positive_experiences.append(exp)
                
                for exp_dict in data.get("negative", []):
                    exp = Experience(
                        task=exp_dict["task"],
                        action=exp_dict["action"],
                        result=exp_dict["result"],
                        success=False,
                        feedback=exp_dict.get("feedback", "")
                    )
                    exp.timestamp = exp_dict.get("timestamp", 0)
                    exp.confidence = exp_dict.get("confidence", 0.0)
                    self.negative_experiences.append(exp)
            
            logger.info(f"加载经验成功: {len(self.positive_experiences)} 条成功, {len(self.negative_experiences)} 条失败")
        except FileNotFoundError:
            logger.info("经验文件不存在，从空开始")
        except Exception as e:
            logger.error(f"加载经验失败: {e}")

    def find_similar_experiences(self, task: str, top_k: int = 5) -> List[Experience]:
        """查找相似经验"""
        all_experiences = self.positive_experiences + self.negative_experiences
        
        # 简单的关键词匹配
        similar = []
        task_lower = task.lower()
        
        for exp in all_experiences:
            if task_lower in exp.task.lower() or exp.task.lower() in task_lower:
                similar.append(exp)
        
        # 按时间排序
        similar.sort(key=lambda x: x.timestamp, reverse=True)
        return similar[:top_k]


class LearningEngine:
    """学习引擎"""

    def __init__(self):
        self.experience_memory = ExperienceMemory()
        self.rules = {}  # 学到的规则
        self._learn_from_experiences()

    def record_experience(self, task: str, action: str, result: str, success: bool, feedback: str = ""):
        """记录经验"""
        exp = Experience(task, action, result, success, feedback)
        self.experience_memory.add_experience(exp)
        
        # 立即学习
        self._learn_from_new_experience(exp)

    def _learn_from_new_experience(self, experience: Experience):
        """从新经验中学习"""
        # 提取规则
        if experience.success:
            self._extract_positive_rule(experience)
        else:
            self._extract_negative_rule(experience)

    def _extract_positive_rule(self, experience: Experience):
        """从成功经验中提取规则"""
        # 简单规则提取：任务类型 -> 成功动作
        task_type = self._classify_task(experience.task)
        
        if task_type not in self.rules:
            self.rules[task_type] = {"success": [], "failure": []}
        
        action_pattern = experience.action
        if action_pattern not in self.rules[task_type]["success"]:
            self.rules[task_type]["success"].append(action_pattern)
            logger.info(f"学到新规则: {task_type} -> {action_pattern}")

    def _extract_negative_rule(self, experience: Experience):
        """从失败经验中提取规则"""
        task_type = self._classify_task(experience.task)
        
        if task_type not in self.rules:
            self.rules[task_type] = {"success": [], "failure": []}
        
        action_pattern = experience.action
        if action_pattern not in self.rules[task_type]["failure"]:
            self.rules[task_type]["failure"].append(action_pattern)
            logger.info(f"学到避免规则: {task_type} -> 避免 {action_pattern}")

    def _classify_task(self, task: str) -> str:
        """分类任务类型"""
        task_lower = task.lower()
        
        if "爬取" in task_lower or "网页" in task_lower:
            return "web_crawling"
        elif "分析" in task_lower or "数据" in task_lower:
            return "analysis"
        elif "写" in task_lower or "文章" in task_lower:
            return "writing"
        elif "搜索" in task_lower:
            return "search"
        elif "总结" in task_lower:
            return "summarization"
        else:
            return "other"

    def _learn_from_experiences(self):
        """从已有经验中学习"""
        for exp in self.experience_memory.positive_experiences:
            self._extract_positive_rule(exp)
        
        for exp in self.experience_memory.negative_experiences:
            self._extract_negative_rule(exp)

    def suggest_action(self, task: str) -> Optional[str]:
        """根据经验建议动作"""
        task_type = self._classify_task(task)
        
        if task_type in self.rules and self.rules[task_type]["success"]:
            # 返回最常用的成功动作
            return self.rules[task_type]["success"][0]
        
        # 查找相似经验
        similar = self.experience_memory.find_similar_experiences(task)
        if similar:
            # 返回最近成功经验的动作
            success_exps = [e for e in similar if e.success]
            if success_exps:
                return success_exps[0].action
        
        return None

    def should_avoid(self, task: str, action: str) -> bool:
        """判断是否应该避免某个动作"""
        task_type = self._classify_task(task)
        
        if task_type in self.rules:
            return action in self.rules[task_type].get("failure", [])
        
        return False

    def get_learning_stats(self) -> Dict:
        """获取学习统计"""
        return {
            "total_experiences": len(self.experience_memory.positive_experiences) + len(self.experience_memory.negative_experiences),
            "positive_experiences": len(self.experience_memory.positive_experiences),
            "negative_experiences": len(self.experience_memory.negative_experiences),
            "learned_rules": len(self.rules),
            "task_types": list(self.rules.keys())
        }


class ContinuousLearner:
    """持续学习者"""

    def __init__(self):
        self.learning_engine = LearningEngine()
        self.improvement_threshold = 0.7  # 改进阈值

    async def learn_from_execution(self, task: str, action: str, result: str, success: bool):
        """从执行结果中学习"""
        self.learning_engine.record_experience(task, action, result, success)
        logger.info(f"记录经验: {'成功' if success else '失败'} - {task}")

    async def get_recommendation(self, task: str) -> Dict:
        """获取任务推荐"""
        suggestion = self.learning_engine.suggest_action(task)
        stats = self.learning_engine.get_learning_stats()
        
        return {
            "suggested_action": suggestion,
            "has_experience": suggestion is not None,
            "stats": stats
        }

    async def evaluate_and_improve(self, task: str, action: str, result: str, success: bool):
        """评估并改进"""
        # 记录经验
        await self.learn_from_execution(task, action, result, success)
        
        # 如果失败，查找替代方案
        if not success:
            similar = self.learning_engine.experience_memory.find_similar_experiences(task)
            success_actions = [e.action for e in similar if e.success]
            
            if success_actions:
                return {
                    "improved": True,
                    "suggestion": success_actions[0],
                    "reason": f"之前执行失败，建议尝试: {success_actions[0]}"
                }
        
        return {"improved": False, "suggestion": None, "reason": "无需改进"}

    def get_learning_summary(self) -> str:
        """获取学习总结"""
        stats = self.learning_engine.get_learning_stats()
        
        summary = f"""学习总结:
- 总经验数: {stats['total_experiences']}
  - 成功经验: {stats['positive_experiences']}
  - 失败经验: {stats['negative_experiences']}
- 已学规则数: {stats['learned_rules']}
- 任务类型: {', '.join(stats['task_types'])}"""
        
        return summary


# ========================================================
# 全局单例
# ========================================================

_learner_instance = None

def get_learner() -> ContinuousLearner:
    """获取持续学习者全局单例"""
    global _learner_instance
    if _learner_instance is None:
        _learner_instance = ContinuousLearner()
    return _learner_instance