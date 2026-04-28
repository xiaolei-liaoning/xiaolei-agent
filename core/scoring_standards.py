"""评分标准配置模块

提供灵活的评分标准管理:
- 内置多种场景预设(通用/代码/数学/创意/专业)
- 支持自定义评分维度和权重
- 动态加载和切换评分标准
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ScoringScenario(Enum):
    """评分场景枚举"""
    GENERAL = "general"              # 通用场景
    CODE = "code"                    # 代码生成
    MATH = "math"                    # 数学计算
    CREATIVE = "creative"            # 创意写作
    PROFESSIONAL = "professional"    # 专业领域(法律/医疗等)
    DATA_ANALYSIS = "data_analysis"  # 数据分析


@dataclass
class ScoringDimension:
    """评分维度定义"""
    name: str                    # 维度名称
    description: str             # 维度描述
    max_score: int               # 满分值
    weight: float                # 权重(0-1)
    criteria: List[str] = field(default_factory=list)  # 评分标准列表
    
    def __post_init__(self):
        """验证权重合法性"""
        if not (0 <= self.weight <= 1):
            raise ValueError(f"权重必须在0-1之间,当前值: {self.weight}")
        if self.max_score <= 0:
            raise ValueError(f"满分必须大于0,当前值: {self.max_score}")


@dataclass
class ScoringStandard:
    """评分标准配置"""
    scenario: ScoringScenario           # 应用场景
    name: str                          # 标准名称
    description: str                   # 标准描述
    dimensions: List[ScoringDimension] # 评分维度列表
    pass_threshold: int = 80           # 合格分数线
    excellent_threshold: int = 90      # 优秀分数线
    
    def __post_init__(self):
        """验证配置合法性"""
        # 检查权重总和
        total_weight = sum(d.weight for d in self.dimensions)
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"权重总和必须为1.0,当前值: {total_weight}")
        
        # 检查总分是否为100
        total_max_score = sum(d.max_score for d in self.dimensions)
        if total_max_score != 100:
            raise ValueError(f"维度满分总和必须为100,当前值: {total_max_score}")
    
    @property
    def dimension_names(self) -> List[str]:
        """获取所有维度名称"""
        return [d.name for d in self.dimensions]
    
    def get_dimension(self, name: str) -> Optional[ScoringDimension]:
        """根据名称获取维度"""
        for dim in self.dimensions:
            if dim.name == name:
                return dim
        return None


class ScoringStandardManager:
    """评分标准管理器
    
    职责:
    1. 管理多种评分标准预设
    2. 支持自定义评分标准
    3. 提供标准切换和查询功能
    """
    
    def __init__(self):
        self.standards: Dict[ScoringScenario, ScoringStandard] = {}
        self._initialize_presets()
    
    def _initialize_presets(self):
        """初始化内置评分标准预设"""
        
        # 1. 通用场景标准
        general_standard = ScoringStandard(
            scenario=ScoringScenario.GENERAL,
            name="通用评分标准",
            description="适用于日常对话、知识问答等通用场景",
            dimensions=[
                ScoringDimension(
                    name="事实准确",
                    description="信息真实可靠,无编造内容",
                    max_score=40,
                    weight=0.4,
                    criteria=[
                        "信息真实可靠,有依据",
                        "数据准确,引用来源可信",
                        "无明显事实错误"
                    ]
                ),
                ScoringDimension(
                    name="逻辑通顺",
                    description="推理过程清晰合理,前后一致",
                    max_score=30,
                    weight=0.3,
                    criteria=[
                        "推理过程清晰",
                        "前后逻辑一致",
                        "无矛盾或跳跃"
                    ]
                ),
                ScoringDimension(
                    name="贴合问题",
                    description="直接回答用户核心诉求",
                    max_score=20,
                    weight=0.2,
                    criteria=[
                        "直接回应用户问题",
                        "无答非所问",
                        "覆盖问题关键点"
                    ]
                ),
                ScoringDimension(
                    name="无幻觉",
                    description="不虚构不存在的信息",
                    max_score=10,
                    weight=0.1,
                    criteria=[
                        "不编造虚假信息",
                        "不确定时明确说明",
                        "避免过度推测"
                    ]
                )
            ],
            pass_threshold=80,
            excellent_threshold=90
        )
        
        # 2. 代码生成标准
        code_standard = ScoringStandard(
            scenario=ScoringScenario.CODE,
            name="代码生成评分标准",
            description="适用于代码编写、调试、优化等技术场景",
            dimensions=[
                ScoringDimension(
                    name="代码正确性",
                    description="代码可运行,无语法错误",
                    max_score=35,
                    weight=0.35,
                    criteria=[
                        "语法正确,可编译/解释",
                        "逻辑正确,能实现预期功能",
                        "边界条件处理完善"
                    ]
                ),
                ScoringDimension(
                    name="代码质量",
                    description="代码结构清晰,符合最佳实践",
                    max_score=25,
                    weight=0.25,
                    criteria=[
                        "变量命名规范",
                        "代码结构清晰",
                        "遵循语言惯例"
                    ]
                ),
                ScoringDimension(
                    name="注释文档",
                    description="关键逻辑有注释,易于理解",
                    max_score=20,
                    weight=0.2,
                    criteria=[
                        "关键逻辑有注释",
                        "函数/类有文档字符串",
                        "复杂算法有说明"
                    ]
                ),
                ScoringDimension(
                    name="性能优化",
                    description="考虑时间/空间复杂度",
                    max_score=20,
                    weight=0.2,
                    criteria=[
                        "算法效率合理",
                        "无明显性能瓶颈",
                        "资源使用高效"
                    ]
                )
            ],
            pass_threshold=75,
            excellent_threshold=85
        )
        
        # 3. 数学计算标准
        math_standard = ScoringStandard(
            scenario=ScoringScenario.MATH,
            name="数学计算评分标准",
            description="适用于数学题解答、公式推导等场景",
            dimensions=[
                ScoringDimension(
                    name="计算准确性",
                    description="计算结果正确,无算术错误",
                    max_score=40,
                    weight=0.4,
                    criteria=[
                        "最终答案正确",
                        "中间步骤计算无误",
                        "单位换算正确"
                    ]
                ),
                ScoringDimension(
                    name="解题思路",
                    description="解题方法合理,步骤清晰",
                    max_score=30,
                    weight=0.3,
                    criteria=[
                        "解题方法正确",
                        "步骤完整清晰",
                        "逻辑推导严密"
                    ]
                ),
                ScoringDimension(
                    name="公式应用",
                    description="公式选择恰当,应用正确",
                    max_score=20,
                    weight=0.2,
                    criteria=[
                        "公式选择正确",
                        "公式应用恰当",
                        "变形推导无误"
                    ]
                ),
                ScoringDimension(
                    name="表达规范",
                    description="数学符号使用规范,排版清晰",
                    max_score=10,
                    weight=0.1,
                    criteria=[
                        "符号使用规范",
                        "排版清晰易读",
                        "格式符合要求"
                    ]
                )
            ],
            pass_threshold=80,
            excellent_threshold=90
        )
        
        # 4. 创意写作标准
        creative_standard = ScoringStandard(
            scenario=ScoringScenario.CREATIVE,
            name="创意写作评分标准",
            description="适用于故事创作、文案撰写等创意场景",
            dimensions=[
                ScoringDimension(
                    name="创意性",
                    description="内容新颖独特,有想象力",
                    max_score=30,
                    weight=0.3,
                    criteria=[
                        "构思新颖独特",
                        "富有想象力",
                        "避免陈词滥调"
                    ]
                ),
                ScoringDimension(
                    name="语言表达",
                    description="文字流畅,富有感染力",
                    max_score=30,
                    weight=0.3,
                    criteria=[
                        "语言流畅自然",
                        "用词精准生动",
                        "句式变化丰富"
                    ]
                ),
                ScoringDimension(
                    name="结构完整",
                    description="情节/论证结构完整",
                    max_score=25,
                    weight=0.25,
                    criteria=[
                        "开头引人入胜",
                        "主体充实饱满",
                        "结尾有力收束"
                    ]
                ),
                ScoringDimension(
                    name="主题契合",
                    description="紧扣主题,中心突出",
                    max_score=15,
                    weight=0.15,
                    criteria=[
                        "紧扣给定主题",
                        "中心思想明确",
                        "无偏离主题"
                    ]
                )
            ],
            pass_threshold=75,
            excellent_threshold=85
        )
        
        # 5. 专业领域标准
        professional_standard = ScoringStandard(
            scenario=ScoringScenario.PROFESSIONAL,
            name="专业领域评分标准",
            description="适用于法律、医疗、金融等专业领域",
            dimensions=[
                ScoringDimension(
                    name="专业准确性",
                    description="专业知识准确,符合行业规范",
                    max_score=40,
                    weight=0.4,
                    criteria=[
                        "专业术语使用准确",
                        "符合行业规范和标准",
                        "无专业性错误"
                    ]
                ),
                ScoringDimension(
                    name="逻辑严谨性",
                    description="论证严密,推理充分",
                    max_score=25,
                    weight=0.25,
                    criteria=[
                        "论证逻辑严密",
                        "推理过程充分",
                        "结论有据可依"
                    ]
                ),
                ScoringDimension(
                    name="合规性",
                    description="符合相关法律法规和伦理要求",
                    max_score=20,
                    weight=0.2,
                    criteria=[
                        "符合法律法规",
                        "遵循职业道德",
                        "无违规内容"
                    ]
                ),
                ScoringDimension(
                    name="实用性",
                    description="建议可行,具有实操价值",
                    max_score=15,
                    weight=0.15,
                    criteria=[
                        "建议切实可行",
                        "具有实操指导意义",
                        "考虑实际约束条件"
                    ]
                )
            ],
            pass_threshold=85,
            excellent_threshold=92
        )
        
        # 6. 数据分析标准
        data_analysis_standard = ScoringStandard(
            scenario=ScoringScenario.DATA_ANALYSIS,
            name="数据分析评分标准",
            description="适用于数据统计、趋势分析等场景",
            dimensions=[
                ScoringDimension(
                    name="数据准确性",
                    description="数据处理正确,统计方法恰当",
                    max_score=35,
                    weight=0.35,
                    criteria=[
                        "数据采集完整",
                        "处理方法正确",
                        "统计指标准确"
                    ]
                ),
                ScoringDimension(
                    name="分析深度",
                    description="洞察深入,发现关键规律",
                    max_score=30,
                    weight=0.3,
                    criteria=[
                        "分析角度全面",
                        "洞察深入有价值",
                        "发现关键规律"
                    ]
                ),
                ScoringDimension(
                    name="可视化呈现",
                    description="图表清晰,信息传达有效",
                    max_score=20,
                    weight=0.2,
                    criteria=[
                        "图表类型恰当",
                        "视觉呈现清晰",
                        "信息传达有效"
                    ]
                ),
                ScoringDimension(
                    name="结论建议",
                    description="结论明确,建议 actionable",
                    max_score=15,
                    weight=0.15,
                    criteria=[
                        "结论基于数据",
                        "建议具体可执行",
                        "考虑实施成本"
                    ]
                )
            ],
            pass_threshold=80,
            excellent_threshold=88
        )
        
        # 注册所有预设标准
        self.standards = {
            ScoringScenario.GENERAL: general_standard,
            ScoringScenario.CODE: code_standard,
            ScoringScenario.MATH: math_standard,
            ScoringScenario.CREATIVE: creative_standard,
            ScoringScenario.PROFESSIONAL: professional_standard,
            ScoringScenario.DATA_ANALYSIS: data_analysis_standard
        }
    
    def get_standard(self, scenario: ScoringScenario) -> ScoringStandard:
        """获取指定场景的评分标准
        
        Args:
            scenario: 评分场景
        
        Returns:
            ScoringStandard: 评分标准配置
        
        Raises:
            KeyError: 场景不存在
        """
        if scenario not in self.standards:
            raise KeyError(f"未找到场景 '{scenario.value}' 的评分标准")
        return self.standards[scenario]
    
    def list_standards(self) -> List[Dict[str, str]]:
        """列出所有可用的评分标准
        
        Returns:
            评分标准列表
        """
        return [
            {
                "scenario": s.scenario.value,
                "name": s.name,
                "description": s.description,
                "dimensions": s.dimension_names,
                "pass_threshold": s.pass_threshold
            }
            for s in self.standards.values()
        ]
    
    def register_custom_standard(self, standard: ScoringStandard):
        """注册自定义评分标准
        
        Args:
            standard: 自定义评分标准
        
        Raises:
            ValueError: 标准配置不合法
        """
        # 验证标准合法性(通过__post_init__)
        _ = standard.dimensions  # 触发验证
        
        self.standards[standard.scenario] = standard
    
    def generate_evaluation_prompt(self, scenario: ScoringScenario, 
                                  content: str, 
                                  user_query: str) -> str:
        """生成评审提示词
        
        Args:
            scenario: 评分场景
            content: 待评审内容
            user_query: 用户原始问题
        
        Returns:
            完整的评审提示词
        """
        standard = self.get_standard(scenario)
        
        # 构建维度说明
        dimension_descriptions = []
        for i, dim in enumerate(standard.dimensions, 1):
            criteria_text = "\n".join([f"   - {c}" for c in dim.criteria])
            dimension_descriptions.append(
                f"{i}. {dim.name} ({dim.max_score}分)\n"
                f"   {dim.description}\n"
                f"{criteria_text}"
            )
        
        dimensions_text = "\n\n".join(dimension_descriptions)
        
        prompt = f"""
你现在是内容评审官,请严格按照以下评分标准进行打分。

【评分标准】{standard.name}
{standard.description}

【评分维度】(满分100分,合格线{standard.pass_threshold}分)

{dimensions_text}

【待评测内容】
{content}

【用户原始问题】
{user_query}

【输出格式】
请严格按以下格式输出:

得分：[数字]
问题：
- [问题1]
- [问题2]
优化建议：
- [建议1]
- [建议2]

注意:
1. 得分必须是0-100之间的整数
2. 问题和建议要具体可执行
3. 每个维度都要考虑到
"""
        return prompt


# ==================== 全局单例 ====================

_scoring_manager = ScoringStandardManager()

def get_scoring_manager() -> ScoringStandardManager:
    """获取评分标准管理器单例"""
    return _scoring_manager
