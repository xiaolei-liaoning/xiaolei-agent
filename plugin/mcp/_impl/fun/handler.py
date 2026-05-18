"""趣味技能处理器"""

from typing import Dict, Any


class FunSkill:
    """趣味技能 - 提供笑话、冷知识、运势等功能"""

    def __init__(self):
        # 预加载笑话库
        self.jokes = [
            "为什么程序员总是分不清万圣节和圣诞节？\n\n因为 Oct 31 == Dec 25",
            "一个PHP程序员对另一个说：\n我昨晚做了一个梦，梦见我成了亿万富翁！\n另一个问：那你开心吗？\n程序员说：不开行，梦醒后还得回办公室上班。",
            "Q: 为什么数据库管理员从不笑？\nA: 因为他们总是担心索引损坏 (索引总是抖动的 😅)",
            "两个量子物理学家走进酒吧。\n酒保问：'你们要喝什么？'\n一个说：'我要来一杯不可观测的酒'\n酒保愣了一下说：'抱歉，我们现在就关门了'",
            "Q: 如何用一行代码创建一个空字典？\nA: {} (但你要先把它的括号删掉)",
        ]

        # 预加载冷知识库
        self.facts = [
            "海星有9个大脑！一个在身体中心，其他8个在每条腿的尖端。",
            "章鱼有三颗心脏！两颗负责将血液泵入鳃，一颗泵入身体其余部分。",
            "蜂蜜永远不会变质。考古学家在古埃及墓穴中发现的蜂蜜仍然可以食用。",
            "香蕉是浆果，但草莓不是！从植物学角度来说，浆果必须有从花托发育而来的外果皮。",
            "你的鼻子和耳朵在你的一生中都会继续生长。",
        ]

        # 运势数据库
        self.fortunes = [
            "🌟 今日运势：会有意外的好消息从天而降！",
            "🍀 今日运势：保持耐心，耐心会带来好运。",
            "💡 今日运势：适合学习新技能，今天的大脑格外灵活。",
            "⚡ 今日运势：今天你的直觉非常准，相信自己的第一感觉。",
            "🌙 今日运势：适合独处思考，今晚会收获很多。",
        ]

    async def handle(self, action: str, params: Dict[str, Any]) -> str:
        """处理趣味请求

        Args:
            action: 趣味类型 (joke, fact, fortune)
            params: 参数

        Returns:
            趣味内容
        """
        handlers = {
            "joke": self._joke,
            "fact": self._fact,
            "fortune": self._fortune,
        }

        handler = handlers.get(action)
        if not handler:
            return f"未知的趣味类型: {action}。可用类型: joke (笑话), fact (冷知识), fortune (运势)"

        return await handler(params)

    async def _joke(self, params: Dict[str, Any]) -> str:
        """获取一个笑话"""
        import random

        count = params.get("count", 1)

        try:
            n = int(count)
            n = max(1, min(n, 5))  # 限制数量1-5
        except ValueError:
            n = 1

        jokes = []
        for _ in range(n):
            jokes.append(random.choice(self.jokes))

        if n == 1:
            return f"😂 {jokes[0]}"
        return "\n\n".join(f"{i+1}. {j}" for i, j in enumerate(jokes))

    async def _fact(self, params: Dict[str, Any]) -> str:
        """获取一个冷知识"""
        import random

        count = params.get("count", 1)

        try:
            n = int(count)
            n = max(1, min(n, 5))  # 限制数量1-5
        except ValueError:
            n = 1

        facts = []
        for _ in range(n):
            facts.append(random.choice(self.facts))

        if n == 1:
            return f"🧠 {facts[0]}"
        return "\n\n".join(f"{i+1}. {f}" for i, f in enumerate(facts))

    async def _fortune(self, params: Dict[str, Any]) -> str:
        """获取运势"""
        import random

        return random.choice(self.fortunes)
