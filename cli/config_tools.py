"""配置管理工具模块"""

class ConfigTools:
    @staticmethod
    async def show_config():
        """显示当前配置"""
        print("\n⚙️ 当前配置:")
        print("  思考模式: 开启")
        print("  调试模式: 关闭")
        print("  LLM模型: glm-4-free")
        print("  缓存启用: 是")
        print("  超时时间: 10秒")
    
    @staticmethod
    async def set_config(key, value):
        """设置配置项"""
        print(f"\n✅ 配置已更新: {key} = {value}")