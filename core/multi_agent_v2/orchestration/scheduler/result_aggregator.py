"""
结果聚合器 - 多Agent执行结果的去重、冲突解决与质量评分

功能：
1. 去重 - 使用编辑距离检测并移除相似结果
2. Conflict Resolution - 按置信度/成功率投票解决冲突
3. 质量评分 - 综合多个维度量化结果质量
4. 摘要生成 - 使用LLM或模板生成结果摘要
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResultAggregator:
    """结果聚合器 - 汇总多Agent执行结果

    职责：
    - 对多个Agent返回的结果进行去重（编辑距离）
    - 通过置信度/成功率投票解决冲突
    - 量化评估每个结果的质量（0-1分）
    - 生成聚合结果摘要
    """

    def __init__(self):
        # 去重阈值：编辑距离比例低于此值视为重复
        self.dedup_threshold = 0.3
        # 质量评分权重
        self.quality_weights = {
            "completeness": 0.3,
            "confidence": 0.3,
            "relevance": 0.2,
            "timeliness": 0.2,
        }
        logger.info("结果聚合器初始化完成")

    def aggregate(
        self,
        results: List[Dict[str, Any]],
        task_description: str,
    ) -> Dict[str, Any]:
        """聚合多Agent执行结果

        流程：
        1. 去重 — 移除相似结果
        2. 冲突解决 — 投票或择优
        3. 质量评分 — 每个结果打分
        4. 摘要生成 — 汇总信息

        Args:
            results: 各Agent执行结果列表。每项应包含:
                - agent_id: Agent ID
                - output: 执行输出（字符串）
                - success: 是否成功（bool）
                - confidence: 置信度（float, 0-1）
                - execution_time: 执行时间（float, 秒）
                （可选）agent_type, metrics 等
            task_description: 原始任务描述

        Returns:
            聚合后的结果字典:
                - success: 是否整体成功
                - primary_output: 主输出
                - all_outputs: 全部输出去重后列表
                - quality_scores: 各结果质量分数
                - conflicts: 发现的冲突
                - summary: 文本摘要
                - metadata: 聚合元信息
        """
        if not results:
            return {
                "success": False,
                "primary_output": "",
                "all_outputs": [],
                "quality_scores": {},
                "conflicts": [],
                "summary": "无执行结果",
                "metadata": {"total_results": 0},
            }

        # 1. 去重
        deduped = self._deduplicate(results)
        logger.debug(f"去重: {len(results)} -> {len(deduped)}")

        # 2. 冲突检测与解决
        resolved = self._resolve_conflicts(deduped)

        # 提取冲突标记（_resolve_conflicts 在列表末尾附加冲突信息）
        conflicts = []
        if resolved and isinstance(resolved[-1], dict) and "_conflicts" in resolved[-1]:
            conflicts = resolved[-1]["_conflicts"]
            resolved = resolved[:-1]

        # 3. 质量评分
        quality_scores = {}
        for result in resolved:
            quality_scores[result.get("agent_id", "unknown")] = self._score_quality(result)

        # 4. 选择主要输出（质量最高或置信度最高的）
        best_result = max(resolved, key=lambda r: quality_scores.get(r.get("agent_id", ""), 0)) if resolved else {}

        # 5. 生成摘要
        summary = self._generate_summary(resolved, task_description)

        return {
            "success": best_result.get("success", False) if best_result else False,
            "primary_output": best_result.get("output", "") if best_result else "",
            "all_outputs": [r.get("output", "") for r in resolved],
            "quality_scores": quality_scores,
            "conflicts": conflicts,
            "summary": summary,
            "metadata": {
                "total_results": len(results),
                "deduped_count": len(results) - len(deduped),
                "final_count": len(resolved),
                "best_agent": best_result.get("agent_id", "unknown") if best_result else "unknown",
            },
        }

    def _deduplicate(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """使用编辑距离检测并移除相似结果

        比较每个结果的 output 字段，若编辑距离比例低于阈值则视为重复，
        保留置信度更高的结果。

        Args:
            results: 原始结果列表

        Returns:
            去重后的结果列表
        """
        if len(results) <= 1:
            return results[:]

        deduped = []

        for result in results:
            is_duplicate = False
            output_a = str(result.get("output", "") or "")

            for existing in deduped:
                output_b = str(existing.get("output", "") or "")

                # 如果两个输出都为空，视为重复
                if not output_a and not output_b:
                    is_duplicate = True
                    break

                # 编辑距离比例计算
                if output_a and output_b:
                    distance = self._levenshtein_distance(output_a, output_b)
                    max_len = max(len(output_a), len(output_b))
                    ratio = distance / max_len if max_len > 0 else 0.0

                    if ratio < self.dedup_threshold:
                        # 重复，保留置信度更高的
                        confidence_a = result.get("confidence", 0.5)
                        confidence_b = existing.get("confidence", 0.5)
                        if confidence_a > confidence_b:
                            deduped.remove(existing)
                            deduped.append(result)
                        is_duplicate = True
                        break

            if not is_duplicate:
                deduped.append(result)

        return deduped

    def _resolve_conflicts(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解决结果中的冲突

        当多个Agent对同一任务给出不同结果时，通过以下方式解决：
        - 按置信度投票：置信度更高更可信
        - 按成功率加权：历史上成功率更高的Agent权重更大

        Args:
            results: 待解决的结果列表

        Returns:
            冲突解决后的结果列表
        """
        if len(results) <= 1:
            return results[:]

        # 检测冲突：output差异大且success=True的结果
        conflicts = []
        resolved = []
        seen_outputs = set()

        for result in results:
            output = str(result.get("output", "") or "")
            success = result.get("success", False)

            if not success:
                # 失败的结果跳过
                continue

            # 按置信度排序
            confidence = result.get("confidence", 0.5)
            success_rate = result.get("success_rate", 0.5)

            # 综合评分 = 置信度 * 0.6 + 成功率 * 0.4
            combined_score = confidence * 0.6 + success_rate * 0.4
            result["_combined_score"] = combined_score

            # 检测是否为冲突结果
            output_key = output[:50]  # 用前50字符作为特征
            if output_key in seen_outputs:
                continue  # 相同输出的已处理
            seen_outputs.add(output_key)

            # 检查与其他结果的冲突
            for other in results:
                if other is result and other.get("agent_id") == result.get("agent_id"):
                    continue
                other_output = str(other.get("output", "") or "")
                if other_output and output and other.get("success", False):
                    distance = self._levenshtein_distance(output, other_output)
                    max_len = max(len(output), len(other_output))
                    ratio = distance / max_len if max_len > 0 else 0.0
                    if ratio > 0.5 and ratio < 0.95:
                        # 部分差异，存在冲突
                        conflicts.append({
                            "agent_a": result.get("agent_id"),
                            "agent_b": other.get("agent_id"),
                            "similarity": 1.0 - ratio,
                        })

            resolved.append(result)

        # 按综合评分降序排列
        resolved.sort(key=lambda r: r.get("_combined_score", 0), reverse=True)

        # 清除内部字段
        for r in resolved:
            r.pop("_combined_score", None)

        resolved.append({"_conflicts": conflicts})

        return resolved

    def _score_quality(self, result: Dict[str, Any]) -> float:
        """评分结果质量 (0.0 ~ 1.0)

        综合以下维度：
        - completeness: 输出完整性（内容长度、结构）
        - confidence: Agent自身置信度
        - relevance: 与任务的相关性
        - timeliness: 执行速度

        Args:
            result: 单个执行结果

        Returns:
            质量分数 (0-1)
        """
        output = str(result.get("output", "") or "")
        success = result.get("success", False)
        confidence = result.get("confidence", 0.5)
        execution_time = result.get("execution_time", 0.0)

        # 1. 完整性分：输出长度和质量
        if output:
            # 较长的输出通常更完整（但过长的可能含噪音）
            completeness = min(1.0, len(output) / 500.0)
        else:
            completeness = 0.0

        # 2. 置信度分
        confidence_score = confidence

        # 3. 相关性分：输出中是否包含有意义的内容
        relevance = 0.5
        if output:
            # 至少包含一些实质性内容
            word_count = len(output.split())
            if word_count > 20:
                relevance = 0.8
            elif word_count > 5:
                relevance = 0.6

        # 4. 时效性分：越快越好
        if execution_time > 0:
            # 假设60秒是上限
            timeliness = max(0, 1.0 - execution_time / 60.0)
        else:
            timeliness = 0.5

        # 加权总分
        score = (
            completeness * self.quality_weights["completeness"] +
            confidence_score * self.quality_weights["confidence"] +
            relevance * self.quality_weights["relevance"] +
            timeliness * self.quality_weights["timeliness"]
        )

        # 如果执行失败，最终分数减半
        if not success:
            score *= 0.5

        return round(min(1.0, max(0.0, score)), 4)

    def _generate_summary(
        self,
        results: List[Dict[str, Any]],
        task_description: str,
    ) -> str:
        """生成结果摘要

        从多个结果中提取关键信息，生成可读的文本摘要。

        Args:
            results: 已解决冲突的结果列表
            task_description: 原始任务描述

        Returns:
            文本摘要
        """
        if not results:
            return f"任务「{task_description}」无返回结果"

        successful = [r for r in results if r.get("success", False)]
        failed = [r for r in results if r.get("success") is False]

        parts = [f"任务「{task_description}」执行完成。"]

        if successful:
            parts.append(f"成功: {len(successful)} 个Agent完成执行。")
        if failed:
            parts.append(f"失败: {len(failed)} 个Agent执行失败。")

        # 取最佳结果的前200字符作为预览
        if successful:
            best = max(successful, key=lambda r: r.get("confidence", 0.5))
            output = str(best.get("output", "") or "")
            if output:
                preview = output[:200]
                if len(output) > 200:
                    preview += "..."
                parts.append(f"主要结果: {preview}")

        return "\n".join(parts)

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """计算编辑距离（Levenshtein distance）

        优化的动态规划实现，使用两行滚动数组降低空间复杂度。

        Args:
            s1: 字符串1
            s2: 字符串2

        Returns:
            编辑距离
        """
        if len(s1) < len(s2):
            return ResultAggregator._levenshtein_distance(s2, s1)

        if not s2:
            return len(s1)

        prev_row = list(range(len(s2) + 1))

        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row

        return prev_row[-1]
