"""
Question工具 - 参考Open Code的QuestionTool实现

支持：
- 用户交互
- 选择题
- 多选题
- 自定义输入
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging

from base import Tool, ToolPermission, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


@dataclass
class QuestionOption:
    """问题选项"""
    label: str
    description: Optional[str] = None


@dataclass
class QuestionPrompt:
    """问题提示"""
    question: str
    options: List[QuestionOption] = field(default_factory=list)
    multiple: bool = False
    custom: bool = True  # 是否允许自定义输入
    required: bool = True


@dataclass
class QuestionInput(ToolInput):
    """Question工具输入"""
    questions: List[Dict[str, Any]]


@dataclass
class QuestionOutput(ToolOutput):
    """Question工具输出"""
    answers: List[List[str]]
    message: str


class QuestionTool(Tool[QuestionInput, QuestionOutput]):
    """Question工具 - 参考Open Code的QuestionTool"""

    def __init__(self):
        super().__init__(
            name="question",
            description="Use this tool when you need to ask the user questions during execution. This allows you to gather user preferences, clarify ambiguous instructions, get decisions on implementation choices, or offer choices to the user.",
            permission=ToolPermission.READ,
            timeout=300,  # 5分钟超时
            max_retries=1
        )
        # 存储问题和答案
        self._questions: List[QuestionPrompt] = []
        self._answers: List[List[str]] = []

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"}
                                    },
                                    "required": ["label"]
                                }
                            },
                            "multiple": {"type": "boolean"},
                            "custom": {"type": "boolean"},
                            "required": {"type": "boolean"}
                        },
                        "required": ["question"]
                    },
                    "description": "Questions to ask"
                }
            },
            "required": ["questions"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "message": {"type": "string"}
            }
        }

    def validate_input(self, input_data: Any) -> QuestionInput:
        """验证输入数据"""
        if isinstance(input_data, dict):
            return QuestionInput(questions=input_data.get("questions", []))
        elif isinstance(input_data, QuestionInput):
            return input_data
        else:
            raise ValueError(f"无效的输入类型: {type(input_data)}")

    def execute(self, input_data: QuestionInput) -> QuestionOutput:
        """执行问题询问"""
        # 解析问题
        self._questions = []
        for q_data in input_data.questions:
            options = []
            for opt in q_data.get("options", []):
                if isinstance(opt, str):
                    options.append(QuestionOption(label=opt))
                else:
                    options.append(QuestionOption(
                        label=opt.get("label", ""),
                        description=opt.get("description")
                    ))
            
            question = QuestionPrompt(
                question=q_data.get("question", ""),
                options=options,
                multiple=q_data.get("multiple", False),
                custom=q_data.get("custom", True),
                required=q_data.get("required", True)
            )
            self._questions.append(question)

        # 在实际应用中，这里会调用UI来获取用户输入
        # 这里我们返回一个占位符响应
        self._answers = [[""] for _ in self._questions]

        # 生成响应消息
        formatted = []
        for i, (q, a) in enumerate(zip(self._questions, self._answers)):
            answer_str = ", ".join(a) if a else "Unanswered"
            formatted.append(f'"{q.question}"="{answer_str}"')
        
        message = f"User has answered your questions: {', '.join(formatted)}. You can now continue with the user's answers in mind."

        logger.info(f"问题询问完成: {len(self._questions)} 个问题")

        return QuestionOutput(
            answers=self._answers,
            message=message
        )

    def get_questions(self) -> List[Dict[str, Any]]:
        """获取问题列表"""
        return [
            {
                "question": q.question,
                "options": [{"label": o.label, "description": o.description} for o in q.options],
                "multiple": q.multiple,
                "custom": q.custom,
                "required": q.required
            }
            for q in self._questions
        ]

    def get_answers(self) -> List[List[str]]:
        """获取答案列表"""
        return self._answers

    def set_answers(self, answers: List[List[str]]):
        """设置答案"""
        self._answers = answers


# 注册工具
question_tool = QuestionTool()
