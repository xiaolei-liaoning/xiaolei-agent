"""ASCII艺术技能处理器"""

from typing import Dict, Any


class ArtSkill:
    """ASCII艺术技能 - 提供各种ASCII艺术图案"""

    # ASCII艺术库
    ASCII_ARTS = {
        "cat": r"""
      /\_/\
     ( o.o )
      > ^ <
        """,
        "dog": r"""
       __
      /  \
     |  @  |
     | || ||
     |_^^_|
    /     \
   (___|___)
        """,
        "rocket": r"""
      🚀
     /  \
    |  🌟 |
     \___/
        """,
        "heart": r"""
     ♥  ♥
    ♥  ♥  ♥
   ♥  ♥  ♥  ♥
  ♥  ♥  ♥  ♥  ♥
   ♥  ♥  ♥  ♥
    ♥  ♥  ♥
     ♥  ♥
      ♥
        """,
        "tree": r"""
        | |
       (o.o)
      >  ^  <
     /|   |\
    (_|   |_)
        """,
        "smile": r"""
       😊
      /   \
     ( o o )
      \ v /
     /     \
    |  o  |
     \___/
        """,
        "star": r"""
        *
       /|\
      /*|*\
     /*-*-*-\
    /*-*-*- -*-\
   /*-*-*- -*- -*-\
      -*- -*- -*-
         *
        """,
        "ghost": r"""
         🎃
        /  \
       (    )
       |    |
        \  /
         ⚫
        """,
        "robot": r"""
       /\___/\
      / o   o \
     ( ==  ^  )
      )       (
     /         \
    / (________) \
   |             |
   |             |
   |             |
        """,
        "snowman": r"""
          🎅
          |
         / \
        /   \
       (  o  )
        \___/
        """,
        "flower": r"""
        💐
       /   \
      /_____\
      | ♥ ♥ |
      | ♥ ♥ |
      |  ♥  |
        """,
    }

    def __init__(self):
        # 添加一些彩色的装饰
        self.color_art = {
            "rainbow": "\n".join([
                "  🌈  ",
                " 🌈  🌈  ",
                "🌈  🌈  🌈  ",
                " 🌈  🌈  🌈  ",
                "  🌈  🌈  ",
                "   🌈  🌈  ",
                "    🌈  🌈  ",
            ])
        }

    async def handle(self, action: str, params: Dict[str, Any]) -> str:
        """处理ASCII艺术请求

        Args:
            action: 艺术类型
            params: 参数

        Returns:
            ASCII艺术
        """
        if action == "list":
            return self._list_arts()

        art = self.ASCII_ARTS.get(action)
        if art:
            return art

        # 模糊匹配
        matched = [k for k in self.ASCII_ARTS.keys() if action in k]
        if matched:
            return self.ASCII_ARTS.get(matched[0])

        return f"未知的艺术类型: {action}\n可用类型: {', '.join(self.ASCII_ARTS.keys())}"

    async def _list_arts(self) -> str:
        """列出所有可用的ASCII艺术"""
        arts = []
        for name in sorted(self.ASCII_ARTS.keys()):
            arts.append(name)

        return "🎨 可用的ASCII艺术:\n" + ", ".join(arts)
