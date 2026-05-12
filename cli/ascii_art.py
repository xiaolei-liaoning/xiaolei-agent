"""ASCII艺术模块"""

class ASCIIArt:
    @staticmethod
    async def show_cat():
        """显示猫咪ASCII艺术"""
        cat = """
  /\\_/\\  
 ( o.o ) 
  > ^ <
"""
        print("\n🐱 猫咪")
        print(cat)
    
    @staticmethod
    async def show_dog():
        """显示狗狗ASCII艺术"""
        dog = """
  \\__/  
  (oo)  
  /------\\
 /        \\
|          |
 \\        /
  ------  
"""
        print("\n🐶 狗狗")
        print(dog)
    
    @staticmethod
    async def show_rocket():
        """显示火箭ASCII艺术"""
        rocket = """
     **
    ****
   ******
  ********
 **********
************
     ||
     ||
    ===
"""
        print("\n🚀 火箭")
        print(rocket)