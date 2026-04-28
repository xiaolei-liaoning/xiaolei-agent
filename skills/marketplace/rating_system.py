"""
技能评分系统 - Rating System

提供技能的评分、评论和反馈功能，支持星级评分、用户评价等。
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class Rating:
    """评分记录"""
    
    user_id: str
    skill_name: str
    skill_version: str
    rating: int  # 1-5 星
    comment: str = ""
    created_at: str = ""
    updated_at: str = ""
    helpful_count: int = 0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SkillRatingSummary:
    """技能评分汇总"""
    
    skill_name: str
    average_rating: float = 0.0
    total_ratings: int = 0
    rating_distribution: Dict[int, int] = field(default_factory=lambda: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
    recent_ratings: List[Rating] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'skill_name': self.skill_name,
            'average_rating': round(self.average_rating, 2),
            'total_ratings': self.total_ratings,
            'rating_distribution': self.rating_distribution,
            'recent_ratings': [r.to_dict() for r in self.recent_ratings[:10]]
        }


class RatingSystem:
    """
    评分系统
    
    管理技能的评分和评论，计算平均评分，提供评分统计等功能。
    """
    
    def __init__(self):
        self._ratings: Dict[str, List[Rating]] = {}  # skill_name -> list of ratings
        self._user_ratings: Dict[str, Dict[str, Rating]] = {}  # user_id -> {skill_name: rating}
    
    def add_rating(self, user_id: str, skill_name: str, skill_version: str,
                  rating: int, comment: str = "") -> bool:
        """
        添加评分
        
        Args:
            user_id: 用户ID
            skill_name: 技能名称
            skill_version: 技能版本
            rating: 评分（1-5）
            comment: 评论
            
        Returns:
            bool: 添加是否成功
        """
        # 验证评分范围
        if not 1 <= rating <= 5:
            logger.error(f"Invalid rating: {rating}. Must be between 1 and 5.")
            return False
        
        # 检查用户是否已经评过分
        if user_id in self._user_ratings:
            existing_rating = self._user_ratings[user_id].get(skill_name)
            if existing_rating:
                # 更新现有评分
                return self.update_rating(user_id, skill_name, rating, comment)
        
        # 创建新评分
        new_rating = Rating(
            user_id=user_id,
            skill_name=skill_name,
            skill_version=skill_version,
            rating=rating,
            comment=comment
        )
        
        # 添加到技能评分列表
        if skill_name not in self._ratings:
            self._ratings[skill_name] = []
        
        self._ratings[skill_name].append(new_rating)
        
        # 添加到用户评分记录
        if user_id not in self._user_ratings:
            self._user_ratings[user_id] = {}
        
        self._user_ratings[user_id][skill_name] = new_rating
        
        logger.info(f"User {user_id} rated {skill_name} with {rating} stars")
        return True
    
    def update_rating(self, user_id: str, skill_name: str, 
                     rating: int, comment: str = "") -> bool:
        """
        更新评分
        
        Args:
            user_id: 用户ID
            skill_name: 技能名称
            rating: 新评分
            comment: 新评论
            
        Returns:
            bool: 更新是否成功
        """
        if user_id not in self._user_ratings:
            return False
        
        existing_rating = self._user_ratings[user_id].get(skill_name)
        if not existing_rating:
            return False
        
        # 更新评分
        old_rating = existing_rating.rating
        existing_rating.rating = rating
        existing_rating.comment = comment
        existing_rating.updated_at = datetime.now().isoformat()
        
        logger.info(f"User {user_id} updated rating for {skill_name}: {old_rating} -> {rating}")
        return True
    
    def get_skill_summary(self, skill_name: str) -> SkillRatingSummary:
        """
        获取技能评分汇总
        
        Args:
            skill_name: 技能名称
            
        Returns:
            SkillRatingSummary: 评分汇总
        """
        ratings = self._ratings.get(skill_name, [])
        
        if not ratings:
            return SkillRatingSummary(skill_name=skill_name)
        
        # 计算平均分
        total = sum(r.rating for r in ratings)
        average = total / len(ratings)
        
        # 计算分布
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in ratings:
            distribution[r.rating] = distribution.get(r.rating, 0) + 1
        
        # 获取最近的评分（按时间倒序）
        recent = sorted(ratings, key=lambda r: r.created_at, reverse=True)[:10]
        
        return SkillRatingSummary(
            skill_name=skill_name,
            average_rating=average,
            total_ratings=len(ratings),
            rating_distribution=distribution,
            recent_ratings=recent
        )
    
    def get_user_ratings(self, user_id: str) -> List[Rating]:
        """
        获取用户的所有评分
        
        Args:
            user_id: 用户ID
            
        Returns:
            List[Rating]: 用户的评分列表
        """
        if user_id not in self._user_ratings:
            return []
        
        return list(self._user_ratings[user_id].values())
    
    def mark_helpful(self, user_id: str, skill_name: str, rating_user_id: str) -> bool:
        """
        标记评分为有用
        
        Args:
            user_id: 当前用户ID
            skill_name: 技能名称
            rating_user_id: 评分者用户ID
            
        Returns:
            bool: 操作是否成功
        """
        # 查找该用户的评分
        ratings = self._ratings.get(skill_name, [])
        
        for rating in ratings:
            if rating.user_id == rating_user_id:
                rating.helpful_count += 1
                logger.info(f"User {user_id} marked rating from {rating_user_id} as helpful")
                return True
        
        return False
    
    def get_top_rated_skills(self, min_ratings: int = 5, limit: int = 10) -> List[Dict]:
        """
        获取评分最高的技能
        
        Args:
            min_ratings: 最少评分数量
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 高评分技能列表
        """
        summaries = []
        
        for skill_name in self._ratings.keys():
            summary = self.get_skill_summary(skill_name)
            
            if summary.total_ratings >= min_ratings:
                summaries.append({
                    'skill_name': skill_name,
                    'average_rating': summary.average_rating,
                    'total_ratings': summary.total_ratings
                })
        
        # 按平均分排序
        summaries.sort(key=lambda x: x['average_rating'], reverse=True)
        
        return summaries[:limit]
    
    def get_trending_skills(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """
        获取热门技能（基于近期评分数量）
        
        Args:
            days: 天数范围
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 热门技能列表
        """
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        skill_counts = {}
        
        for skill_name, ratings in self._ratings.items():
            recent_count = sum(
                1 for r in ratings
                if datetime.fromisoformat(r.created_at) > cutoff_date
            )
            
            if recent_count > 0:
                skill_counts[skill_name] = recent_count
        
        # 按评分数量排序
        trending = [
            {'skill_name': name, 'recent_ratings': count}
            for name, count in skill_counts.items()
        ]
        
        trending.sort(key=lambda x: x['recent_ratings'], reverse=True)
        
        return trending[:limit]
    
    def get_statistics(self) -> Dict:
        """获取评分系统统计信息"""
        total_ratings = sum(len(ratings) for ratings in self._ratings.values())
        total_skills = len(self._ratings)
        total_users = len(self._user_ratings)
        
        # 计算全局平均分
        all_ratings = []
        for ratings in self._ratings.values():
            all_ratings.extend([r.rating for r in ratings])
        
        global_average = sum(all_ratings) / len(all_ratings) if all_ratings else 0
        
        return {
            'total_ratings': total_ratings,
            'total_skills_rated': total_skills,
            'total_users': total_users,
            'global_average_rating': round(global_average, 2),
            'average_ratings_per_skill': (
                total_ratings / total_skills if total_skills > 0 else 0
            )
        }
