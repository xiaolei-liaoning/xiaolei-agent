"""小游戏模块"""

class GameModule:
    @staticmethod
    async def play_guess_number():
        """猜数字游戏"""
        import random
        number = random.randint(1, 100)
        attempts = 0
        
        print("\n🎯 猜数字游戏")
        print("我想了一个1-100之间的数字，你猜是多少？")
        
        while True:
            try:
                guess = int(input("你的猜测: "))
                attempts += 1
                
                if guess < number:
                    print("📈 太小了！")
                elif guess > number:
                    print("📉 太大了！")
                else:
                    print(f"🎉 恭喜！你用了 {attempts} 次猜对了！")
                    break
            except ValueError:
                print("❌ 请输入数字！")
    
    @staticmethod
    async def play_rock_paper_scissors():
        """石头剪刀布游戏"""
        import random
        choices = ['石头', '剪刀', '布']
        
        print("\n✊ 石头剪刀布")
        print("输入: 石头/剪刀/布")
        
        user_choice = input("你的选择: ")
        ai_choice = random.choice(choices)
        
        print(f"AI选择: {ai_choice}")
        
        if user_choice == ai_choice:
            print("🤝 平局！")
        elif (user_choice == '石头' and ai_choice == '剪刀') or \
             (user_choice == '剪刀' and ai_choice == '布') or \
             (user_choice == '布' and ai_choice == '石头'):
            print("🎉 你赢了！")
        else:
            print("😢 你输了！")

    @staticmethod
    async def dice_roll():
        """掷骰子"""
        import random
        
        print("\n🎲 掷骰子")
        dice = random.randint(1, 6)
        print(f"你掷出了: {dice}")
        
        if dice == 6:
            print("🎊 大！")
        elif dice == 1:
            print("😔 小！")