"""
技能搜索引擎 - Skill Search Engine

提供技能的智能搜索、过滤和推荐功能。
支持关键词搜索、标签过滤、分类筛选等。
"""

import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from .registry import SkillMetadata, SkillRegistry

logger = logging.getLogger(__name__)


class SkillSearchEngine:
    """
    技能搜索引擎
    
    提供多维度搜索功能，包括关键词匹配、标签过滤、智能推荐等。
    """
    
    def __init__(self, registry: SkillRegistry):
        """
        初始化搜索引擎
        
        Args:
            registry: 技能注册表实例
        """
        self._registry = registry
        self._search_index: Dict[str, List[str]] = defaultdict(list)  # keyword -> [skill_names]
        self._tag_index: Dict[str, List[str]] = defaultdict(list)  # tag -> [skill_names]
        self._category_index: Dict[str, List[str]] = defaultdict(list)  # category -> [skill_names]
        
        # 构建索引
        self._build_index()
    
    def search(self, query: str, 
              category: Optional[str] = None,
              tags: Optional[List[str]] = None,
              min_rating: float = 0,
              verified_only: bool = False,
              limit: int = 20) -> List[Dict]:
        """
        综合搜索
        
        Args:
            query: 搜索关键词
            category: 分类过滤
            tags: 标签过滤
            min_rating: 最低评分
            verified_only: 只返回已验证技能
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 搜索结果列表（包含技能信息和相关性分数）
        """
        # 获取候选技能
        candidate_skills = self._get_candidates(query, category, tags, verified_only)
        
        if not candidate_skills:
            return []
        
        # 计算相关性分数并排序
        scored_skills = []
        
        for skill in candidate_skills:
            # 基础分数
            score = self._calculate_relevance_score(skill, query)
            
            # 应用过滤器
            if min_rating > 0 and skill.rating < min_rating:
                continue
            
            scored_skills.append({
                'skill': skill,
                'score': score
            })
        
        # 按分数排序
        scored_skills.sort(key=lambda x: x['score'], reverse=True)
        
        # 返回结果
        return [
            {
                'skill': item['skill'].to_dict(),
                'relevance_score': round(item['score'], 3)
            }
            for item in scored_skills[:limit]
        ]
    
    def search_by_keywords(self, keywords: List[str], limit: int = 20) -> List[Dict]:
        """
        基于关键词搜索
        
        Args:
            keywords: 关键词列表
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 搜索结果
        """
        skill_scores = defaultdict(float)
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            
            # 从索引中获取相关技能
            matching_skills = self._search_index.get(keyword_lower, [])
            
            for skill_name in matching_skills:
                skill = self._registry.get_skill(skill_name)
                if skill:
                    # 根据匹配位置给予不同权重
                    if keyword_lower in skill.name.lower():
                        skill_scores[skill_name] += 3.0
                    elif keyword_lower in skill.description.lower():
                        skill_scores[skill_name] += 2.0
                    elif keyword_lower in [k.lower() for k in skill.keywords]:
                        skill_scores[skill_name] += 1.5
                    elif any(keyword_lower in tag.lower() for tag in skill.tags):
                        skill_scores[skill_name] += 1.0
        
        # 转换为结果列表
        results = []
        for skill_name, score in skill_scores.items():
            skill = self._registry.get_skill(skill_name)
            if skill:
                results.append({
                    'skill': skill.to_dict(),
                    'relevance_score': round(score, 3)
                })
        
        # 按分数排序
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return results[:limit]
    
    def search_by_tags(self, tags: List[str], limit: int = 20) -> List[Dict]:
        """
        基于标签搜索
        
        Args:
            tags: 标签列表
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 搜索结果
        """
        skill_counts = defaultdict(int)
        
        for tag in tags:
            tag_lower = tag.lower()
            matching_skills = self._tag_index.get(tag_lower, [])
            
            for skill_name in matching_skills:
                skill_counts[skill_name] += 1
        
        # 转换为结果列表
        results = []
        for skill_name, match_count in skill_counts.items():
            skill = self._registry.get_skill(skill_name)
            if skill:
                results.append({
                    'skill': skill.to_dict(),
                    'relevance_score': match_count / len(tags)  # 匹配度
                })
        
        # 按匹配度排序
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return results[:limit]
    
    def search_by_category(self, category: str, limit: int = 20) -> List[Dict]:
        """
        基于分类搜索
        
        Args:
            category: 分类名称
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 搜索结果
        """
        skill_names = self._category_index.get(category.lower(), [])
        
        results = []
        for skill_name in skill_names:
            skill = self._registry.get_skill(skill_name)
            if skill:
                results.append({
                    'skill': skill.to_dict(),
                    'relevance_score': 1.0
                })
        
        # 按评分排序
        results.sort(key=lambda x: x['skill']['rating'], reverse=True)
        
        return results[:limit]
    
    def get_recommendations(self, user_history: List[str], limit: int = 10) -> List[Dict]:
        """
        基于用户历史推荐技能
        
        Args:
            user_history: 用户使用过的技能列表
            limit: 推荐数量
            
        Returns:
            List[Dict]: 推荐技能列表
        """
        if not user_history:
            # 如果没有历史记录，返回热门技能
            return self._get_popular_skills(limit)
        
        # 收集用户历史技能的标签
        user_tags = set()
        for skill_name in user_history:
            skill = self._registry.get_skill(skill_name)
            if skill:
                user_tags.update(skill.tags)
        
        # 基于标签推荐
        recommended = []
        seen_skills = set(user_history)
        
        for tag in user_tags:
            tag_results = self.search_by_tags([tag], limit=5)
            
            for result in tag_results:
                skill_name = result['skill']['name']
                
                if skill_name not in seen_skills:
                    recommended.append(result)
                    seen_skills.add(skill_name)
                    
                    if len(recommended) >= limit:
                        break
            
            if len(recommended) >= limit:
                break
        
        return recommended[:limit]
    
    def get_similar_skills(self, skill_name: str, limit: int = 5) -> List[Dict]:
        """
        获取相似技能
        
        Args:
            skill_name: 参考技能名称
            limit: 返回数量
            
        Returns:
            List[Dict]: 相似技能列表
        """
        reference_skill = self._registry.get_skill(skill_name)
        if not reference_skill:
            return []
        
        # 基于标签相似度
        reference_tags = set(reference_skill.tags)
        
        all_skills = self._registry.list_skills()
        similarities = []
        
        for skill in all_skills:
            if skill.name == skill_name:
                continue
            
            # 计算标签重叠度
            skill_tags = set(skill.tags)
            if reference_tags and skill_tags:
                overlap = len(reference_tags & skill_tags)
                total = len(reference_tags | skill_tags)
                similarity = overlap / total if total > 0 else 0
                
                if similarity > 0:
                    similarities.append({
                        'skill': skill.to_dict(),
                        'similarity': round(similarity, 3)
                    })
        
        # 按相似度排序
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        
        return similarities[:limit]
    
    def _get_candidates(self, query: str, 
                       category: Optional[str],
                       tags: Optional[List[str]],
                       verified_only: bool) -> List[SkillMetadata]:
        """获取候选技能"""
        candidates = []
        
        # 如果有查询词，先进行文本搜索
        if query:
            query_results = self._registry.search_skills(query)
            candidates.extend(query_results)
        else:
            # 否则获取所有技能
            candidates = self._registry.list_skills(verified_only=verified_only)
        
        # 应用分类过滤
        if category:
            candidates = [s for s in candidates if s.category.lower() == category.lower()]
        
        # 应用标签过滤
        if tags:
            candidates = [
                s for s in candidates
                if any(tag.lower() in [t.lower() for t in s.tags] for tag in tags)
            ]
        
        # 去重
        seen = set()
        unique_candidates = []
        for skill in candidates:
            if skill.name not in seen:
                seen.add(skill.name)
                unique_candidates.append(skill)
        
        return unique_candidates
    
    def _calculate_relevance_score(self, skill: SkillMetadata, query: str) -> float:
        """计算相关性分数"""
        score = 0.0
        query_lower = query.lower()
        
        # 名称匹配（最高权重）
        if query_lower in skill.name.lower():
            score += 10.0
        
        # 描述匹配
        if query_lower in skill.description.lower():
            score += 5.0
        
        # 关键词匹配
        for keyword in skill.keywords:
            if query_lower in keyword.lower():
                score += 3.0
                break
        
        # 标签匹配
        for tag in skill.tags:
            if query_lower in tag.lower():
                score += 2.0
                break
        
        # 评分加权
        score *= (1 + skill.rating / 10)
        
        # 下载量加权
        score *= (1 + skill.downloads / 1000)
        
        return score
    
    def _get_popular_skills(self, limit: int) -> List[Dict]:
        """获取热门技能（基于下载量）"""
        all_skills = self._registry.list_skills()
        
        # 按下载量排序
        sorted_skills = sorted(all_skills, key=lambda s: s.downloads, reverse=True)
        
        return [
            {
                'skill': skill.to_dict(),
                'relevance_score': skill.downloads
            }
            for skill in sorted_skills[:limit]
        ]
    
    def _build_index(self):
        """构建搜索索引"""
        all_skills = self._registry.list_skills()
        
        for skill in all_skills:
            # 关键词索引
            for keyword in skill.keywords:
                self._search_index[keyword.lower()].append(skill.name)
            
            # 标签索引
            for tag in skill.tags:
                self._tag_index[tag.lower()].append(skill.name)
            
            # 分类索引
            self._category_index[skill.category.lower()].append(skill.name)
        
        logger.info(f"Built search index with {len(all_skills)} skills")
    
    def get_statistics(self) -> Dict:
        """获取搜索引擎统计信息"""
        return {
            'total_indexed_skills': len(self._registry.list_skills()),
            'keyword_index_size': len(self._search_index),
            'tag_index_size': len(self._tag_index),
            'category_index_size': len(self._category_index),
            'categories': list(self._category_index.keys())
        }
