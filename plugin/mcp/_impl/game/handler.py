"""游戏技能处理器"""

import random
import time
from typing import Dict, Any, Optional


class GameSkill:
    """游戏技能 - 提供多种小游戏"""

    def __init__(self):
        self.guess_number = None
        self.rps_score = {"win": 0, "lose": 0, "draw": 0}
        self.last_dice = None

    async def handle(self, action: str, params: Dict[str, Any]) -> str:
        """处理游戏请求

        Args:
            action: 游戏类型 (guess, rps, dice)
            params: 参数

        Returns:
            游戏结果
        """
        handlers = {
            "guess": self._guess_number,
            "rps": self._rps,
            "dice": self._dice,
        }

        handler = handlers.get(action)
        if not handler:
            return f"未知游戏类型: {action}。可用游戏: guess (猜数字), rps (石头剪刀布), dice (掷骰子)"

        return await handler(params)

    async def _guess_number(self, params: Dict[str, Any]) -> str:
        """猜数字游戏"""
        # 初始化游戏
        if self.guess_number is None or "reset" in params:
            self.guess_number = {
                "target": random.randint(1, 100),
                "attempts": 0,
                "max_attempts": 10
            }

        if "reset" in params:
            self.guess_number = None
            return "🔢 猜数字游戏已重置！\n猜一个1-100之间的数字，你有10次机会。"

        # 获取用户猜测
        guess = params.get("number")
        if guess is None:
            return "🔢 猜数字游戏\n目标数字: 1-100\n请猜测一个数字，或输入 'reset' 重置游戏。"

        try:
            guess = int(guess)
            self.guess_number["attempts"] += 1

            if guess == self.guess_number["target"]:
                self.guess_number = None
                return f"🎉 恭喜！你猜对了！\n数字就是 {self.guess_number['target']}\n总尝试次数: {self.guess_number['attempts']}"

            elif guess < self.guess_number["target"]:
                remaining = self.guess_number["max_attempts"] - self.guess_number["attempts"]
                hint = "再大一点！"
                if remaining <= 0:
                    self.guess_number = None
                    return f"😢 游戏结束！\n正确数字是 {self.guess_number['target']}"
                return f"📈 太小了！{hint} 剩余机会: {remaining}"

            else:
                remaining = self.guess_number["max_attempts"] - self.guess_number["attempts"]
                hint = "再小一点！"
                if remaining <= 0:
                    self.guess_number = None
                    return f"😢 游戏结束！\n正确数字是 {self.guess_number['target']}"
                return f"📉 太大了！{hint} 剩余机会: {remaining}"

        except ValueError:
            return "请输入有效的数字！"

    async def _rps(self, params: Dict[str, Any]) -> str:
        """石头剪刀布游戏"""
        choices = ["石头", "剪刀", "布"]

        if "reset" in params:
            self.rps_score = {"win": 0, "lose": 0, "draw": 0}
            return "✊✋✌️ 石头剪刀布游戏已重置！\n胜负: 0-0-0\n输入 'rock/stone', 'scissors', 'paper' 或 'r/p/s' 开始游戏"

        player = params.get("choice")
        if player is None:
            return "✊✋✌️ 石头剪刀布\n输入你的选择:\n- rock / stone / r (石头)\n- scissors / s (剪刀)\n- paper / p (布)\n输入 'reset' 重置比分"

        # 映射输入到选择
        player_lower = str(player).lower()
        choice_map = {"rock": 0, "stone": 0, "r": 0, "石头": 0,
                      "scissors": 1, "s": 1, "剪刀": 1,
                      "paper": 2, "p": 2, "布": 2}
        player_choice = choice_map.get(player_lower, -1)

        if player_choice == -1:
            return "无效选择！请输入: rock/stone/r, scissors/s, paper/p"

        # AI随机选择
        ai_choice = random.randint(0, 2)

        # 判断胜负
        results = ["draw", "win", "lose"]
        player_wins = (player_choice + 1) % 3 == ai_choice
        ai_wins = (ai_choice + 1) % 3 == player_choice

        if player_choice == ai_choice:
            result = "draw"
            self.rps_score["draw"] += 1
            msg = "🤝 平局！"
        elif player_wins:
            result = "win"
            self.rps_score["win"] += 1
            msg = "🎉 你赢了！"
        else:
            result = "lose"
            self.rps_score["lose"] += 1
            msg = "😢 你输了！"

        choice_names = choices
        return f"{msg}\n\n你出: {choice_names[player_choice]}\nAI出: {choice_names[ai_choice]}\n\n当前比分: {self.rps_score['win']}-{self.rps_score['lose']}-{self.rps_score['draw']}"

    async def _dice(self, params: Dict[str, Any]) -> str:
        """掷骰子游戏"""
        if "reset" in params:
            self.last_dice = None
            return "🎲 骰子游戏已重置！\n输入 'roll' 或 '1d6' 掷一个6面骰子\n输入 '2d6' 掷两个骰子"

        rolls = params.get("rolls", "1d6")

        if not isinstance(rolls, str):
            return "请输入骰子表达式，如: 1d6, 2d6"

        # 解析骰子表达式
        if "d" in rolls:
            try:
                parts = rolls.split("d")
                if len(parts) == 2:
                    count = int(parts[0]) or 1
                    sides = int(parts[1]) or 6
                    count = min(count, 100)  # 限制最大数量
                else:
                    count, sides = 1, 6
            except ValueError:
                return "无效的骰子表达式！格式: nds (如 2d6)"
        else:
            count, sides = 1, 6

        # 掷骰子
        results = [random.randint(1, sides) for _ in range(count)]
        total = sum(results)
        max_roll = sides * count

        msg = f"🎲 掷骰子: {count}d{sides}\n结果: {results}\n总计: {total}"

        if count == 1:
            if results[0] in [1, 2]:
                msg += " 🍀 小运！"
            elif results[0] in [5, 6]:
                msg += " ✨ 大运！"

        if max_roll <= 12:
            msg += f"\n(最大值: {max_roll})"
        else:
            msg += f"\n(1d{max_roll})"

        return msg
