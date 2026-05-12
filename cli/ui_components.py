"""终端UI组件模块 - Claude Code风格

提供丰富的终端UI组件，包括进度条、表格、卡片、动画等。

组件列表:
1. ProgressBar - 进度条
2. Table - 表格
3. Card - 卡片
4. Spinner - 加载动画
5. Tree - 树形结构
6. StatusBar - 状态栏
7. Menu - 菜单
8. Dialog - 对话框
"""

import sys
import time
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from cli.colors import CliColors, print_color


class SpinnerType(Enum):
    """加载动画类型"""
    LINE = "line"
    DOT = "dot"
    BAR = "bar"
    PULSE = "pulse"


class ProgressBar:
    """进度条组件"""
    
    def __init__(self, total: int = 100, width: int = 40, show_percent: bool = True):
        self.total = total
        self.width = width
        self.show_percent = show_percent
        self.current = 0
    
    def update(self, current: int):
        """更新进度"""
        self.current = min(current, self.total)
        percent = (self.current / self.total) * 100
        filled = int(self.width * percent / 100)
        
        bar = "█" * filled + "░" * (self.width - filled)
        percent_str = f" {percent:.1f}%" if self.show_percent else ""
        
        sys.stdout.write(f"\r{CliColors.CYAN}[{bar}]{percent_str}{CliColors.ENDC}")
        sys.stdout.flush()
    
    def complete(self):
        """完成进度"""
        self.update(self.total)
        print()


class Table:
    """表格组件 - 支持排序和分页"""
    
    def __init__(self, headers: List[str], data: List[List[Any]] = None, border: bool = True):
        self.headers = headers
        self.data = data or []
        self.border = border
        self.column_widths = []
        self.sort_column = None
        self.sort_ascending = True
        self.current_page = 1
        self.page_size = 10
    
    def _calculate_column_widths(self, data):
        """计算列宽"""
        self.column_widths = []
        for i, header in enumerate(self.headers):
            max_width = len(str(header))
            for row in data:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            self.column_widths.append(max_width + 2)
    
    def add_row(self, row: List[Any]):
        """添加行"""
        self.data.append(row)
    
    def sort(self, column_index: int, ascending: bool = True):
        """按指定列排序"""
        if 0 <= column_index < len(self.headers):
            self.sort_column = column_index
            self.sort_ascending = ascending
            self.data.sort(key=lambda x: str(x[column_index]) if column_index < len(x) else "", reverse=not ascending)
            self.current_page = 1
    
    def get_total_pages(self) -> int:
        """获取总页数"""
        if self.page_size <= 0:
            return 1
        return (len(self.data) + self.page_size - 1) // self.page_size
    
    def set_page(self, page: int):
        """设置当前页"""
        total_pages = self.get_total_pages()
        self.current_page = max(1, min(page, total_pages))
    
    def get_page_data(self) -> List[List[Any]]:
        """获取当前页数据"""
        if self.page_size <= 0:
            return self.data
        start = (self.current_page - 1) * self.page_size
        end = start + self.page_size
        return self.data[start:end]
    
    def render(self, show_pagination: bool = True):
        """渲染表格"""
        page_data = self.get_page_data()
        self._calculate_column_widths(page_data)
        
        if self.border:
            print_color("┌" + "┬".join("─" * w for w in self.column_widths) + "┐", CliColors.GRAY)
        
        header_cells = []
        for i, header in enumerate(self.headers):
            sort_indicator = ""
            if self.sort_column == i:
                sort_indicator = " ↑" if self.sort_ascending else " ↓"
            header_cells.append(f" {header.ljust(self.column_widths[i] - 2 - len(sort_indicator))}{sort_indicator} ")
        print_color("│" + "│".join(header_cells) + "│", CliColors.BOLD + CliColors.CYAN)
        
        if self.border:
            print_color("├" + "┼".join("─" * w for w in self.column_widths) + "┤", CliColors.GRAY)
        
        for row in page_data:
            cells = []
            for i, cell in enumerate(row):
                width = self.column_widths[i] - 2
                cells.append(f" {str(cell).ljust(width)} ")
            print_color("│" + "│".join(cells) + "│", CliColors.WHITE)
        
        if self.border:
            print_color("└" + "┴".join("─" * w for w in self.column_widths) + "┘", CliColors.GRAY)
        
        if show_pagination and self.page_size > 0 and len(self.data) > self.page_size:
            total_pages = self.get_total_pages()
            pagination_info = f"  第 {self.current_page}/{total_pages} 页 | 共 {len(self.data)} 条记录"
            print_color(pagination_info, CliColors.GRAY)


class Card:
    """卡片组件"""
    
    def __init__(self, title: str = "", content: str = "", color: str = CliColors.BRIGHT_BLUE):
        self.title = title
        self.content = content
        self.color = color
    
    def render(self):
        """渲染卡片"""
        lines = self.content.split('\n')
        max_len = max(len(self.title), max(len(line) for line in lines)) if lines else len(self.title)
        max_len = min(max_len, 60)
        
        # 顶部边框
        print_color(f"╭{self.color}─{'─' * max_len}─╮{CliColors.ENDC}", self.color)
        
        # 标题
        if self.title:
            title_padded = self.title.ljust(max_len)
            print_color(f"│ {self.color}{title_padded}{CliColors.ENDC} │")
            print_color(f"├{self.color}─{'─' * max_len}─┤{CliColors.ENDC}", self.color)
        
        # 内容
        for line in lines:
            line_padded = line.ljust(max_len)
            print_color(f"│ {line_padded} │", CliColors.WHITE)
        
        # 底部边框
        print_color(f"╰{self.color}─{'─' * max_len}─╯{CliColors.ENDC}", self.color)


class Spinner:
    """加载动画组件"""
    
    def __init__(self, text: str = "", spinner_type: SpinnerType = SpinnerType.LINE):
        self.text = text
        self.spinner_type = spinner_type
        self.running = False
        
        self.spinners = {
            SpinnerType.LINE: "|/-\\",
            SpinnerType.DOT: "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏",
            SpinnerType.BAR: "▁▂▃▄▅▆▇█▇▆▅▄▃▂▁",
            SpinnerType.PULSE: "█▉▊▋▌▍▎▏▎▍▌▋▊▉"
        }
    
    def start(self):
        """开始动画"""
        self.running = True
        frames = self.spinners[self.spinner_type]
        
        while self.running:
            for frame in frames:
                if not self.running:
                    break
                sys.stdout.write(f"\r{CliColors.YELLOW}{frame}{CliColors.ENDC} {self.text}")
                sys.stdout.flush()
                time.sleep(0.1)
    
    def stop(self):
        """停止动画"""
        self.running = False
        sys.stdout.write("\r" + " " * (len(self.text) + 2) + "\r")
        sys.stdout.flush()


class Tree:
    """树形结构组件"""
    
    def __init__(self, data: Dict[str, Any]):
        self.data = data
    
    def _render_node(self, node: Dict[str, Any], prefix: str = "", is_last: bool = True):
        """递归渲染节点"""
        name = node.get("name", "")
        children = node.get("children", [])
        
        # 节点前缀
        if prefix:
            if is_last:
                print_color(f"{prefix}└── {name}", CliColors.CYAN)
                child_prefix = prefix + "    "
            else:
                print_color(f"{prefix}├── {name}", CliColors.CYAN)
                child_prefix = prefix + "│   "
        else:
            print_color(name, CliColors.BOLD + CliColors.CYAN)
            child_prefix = ""
        
        # 递归渲染子节点
        for i, child in enumerate(children):
            self._render_node(child, child_prefix, i == len(children) - 1)
    
    def render(self):
        """渲染树形结构"""
        self._render_node(self.data)


class StatusBar:
    """状态栏组件"""
    
    def __init__(self):
        self.items = []
    
    def add_item(self, text: str, color: str = CliColors.WHITE):
        """添加状态项"""
        self.items.append((text, color))
    
    def render(self):
        """渲染状态栏"""
        print()
        print_color("─" * 80, CliColors.GRAY)
        
        parts = []
        for text, color in self.items:
            parts.append(f"{color}{text}{CliColors.ENDC}")
        
        print("  ".join(parts))
        print_color("─" * 80, CliColors.GRAY)


class Menu:
    """菜单组件"""
    
    def __init__(self, title: str = "", items: List[Dict[str, Any]] = None):
        self.title = title
        self.items = items or []
    
    def add_item(self, key: str, label: str, description: str = ""):
        """添加菜单项"""
        self.items.append({
            "key": key,
            "label": label,
            "description": description
        })
    
    def show(self) -> str:
        """显示菜单并返回用户选择"""
        print()
        if self.title:
            print_color(f"  {self.title}", CliColors.BOLD + CliColors.CYAN)
            print_color("  " + "─" * 40, CliColors.GRAY)
        
        for i, item in enumerate(self.items, 1):
            key = item["key"]
            label = item["label"]
            desc = item.get("description", "")
            
            print_color(f"  {i}. [{key}] {label}", CliColors.WHITE)
            if desc:
                print_color(f"     {desc}", CliColors.GRAY)
        
        print()
        while True:
            choice = input(f"{CliColors.GREEN}请选择 (输入数字或快捷键): {CliColors.ENDC}").strip()
            
            # 尝试数字选择
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(self.items):
                    return self.items[idx]["key"]
            
            # 尝试快捷键选择
            for item in self.items:
                if item["key"].lower() == choice.lower():
                    return item["key"]
            
            print_color("  无效选择，请重新输入", CliColors.RED)


class Dialog:
    """对话框组件"""
    
    @staticmethod
    def confirm(message: str) -> bool:
        """确认对话框"""
        print()
        print_color(f"  {message}", CliColors.YELLOW)
        while True:
            choice = input(f"{CliColors.GREEN}确认? (y/n): {CliColors.ENDC}").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                return False
            print_color("  请输入 y 或 n", CliColors.RED)
    
    @staticmethod
    def info(message: str):
        """信息对话框"""
        print()
        print_color(f"  ℹ️ {message}", CliColors.CYAN)
        input(f"{CliColors.GRAY}按 Enter 继续...{CliColors.ENDC}")
    
    @staticmethod
    def success(message: str):
        """成功对话框"""
        print()
        print_color(f"  ✅ {message}", CliColors.GREEN)
        input(f"{CliColors.GRAY}按 Enter 继续...{CliColors.ENDC}")
    
    @staticmethod
    def error(message: str):
        """错误对话框"""
        print()
        print_color(f"  ❌ {message}", CliColors.RED)
        input(f"{CliColors.GRAY}按 Enter 继续...{CliColors.ENDC}")
    
    @staticmethod
    def prompt(message: str, default: str = "") -> str:
        """输入对话框"""
        print()
        if default:
            result = input(f"{CliColors.CYAN}{message} (默认: {default}): {CliColors.ENDC}")
            return result.strip() or default
        else:
            return input(f"{CliColors.CYAN}{message}: {CliColors.ENDC}").strip()


class Panel:
    """面板组件"""
    
    def __init__(self, title: str = "", width: int = 60):
        self.title = title
        self.width = width
        self.lines = []
    
    def add_line(self, text: str, color: str = CliColors.WHITE):
        """添加行"""
        self.lines.append((text, color))
    
    def render(self):
        """渲染面板"""
        print()
        print_color("╔" + "═" * self.width + "╗", CliColors.BRIGHT_BLUE + CliColors.BOLD)
        
        if self.title:
            padded_title = self.title.center(self.width - 2)
            print_color(f"║{CliColors.BOLD}{padded_title}{CliColors.ENDC}║", CliColors.BRIGHT_BLUE)
            print_color("╠" + "═" * self.width + "╣", CliColors.BRIGHT_BLUE)
        
        for text, color in self.lines:
            padded_text = text.ljust(self.width - 2)[:self.width - 2]
            print_color(f"║{color}{padded_text}{CliColors.ENDC}║", CliColors.BRIGHT_BLUE)
        
        print_color("╚" + "═" * self.width + "╝", CliColors.BRIGHT_BLUE)


class HorizontalRule:
    """分隔线组件"""
    
    @staticmethod
    def render(char: str = "─", length: int = 60, color: str = CliColors.GRAY):
        """渲染分隔线"""
        print_color(char * length, color)


class KeyValueDisplay:
    """键值对显示组件"""
    
    def __init__(self, items: Dict[str, Any] = None):
        self.items = items or {}
    
    def add(self, key: str, value: Any):
        """添加键值对"""
        self.items[key] = value
    
    def render(self, title: str = ""):
        """渲染键值对"""
        if title:
            print_color(f"  {title}", CliColors.BOLD + CliColors.CYAN)
        
        max_key_len = max(len(k) for k in self.items.keys()) if self.items else 0
        
        for key, value in self.items.items():
            key_padded = key.ljust(max_key_len)
            print_color(f"  {key_padded}: {CliColors.GREEN}{value}{CliColors.ENDC}", CliColors.WHITE)


class AnimatedText:
    """动画文本组件"""
    
    @staticmethod
    def typewriter(text: str, delay: float = 0.05, color: str = CliColors.WHITE):
        """打字机效果"""
        for char in text:
            print_color(char, color, end='')
            sys.stdout.flush()
            time.sleep(delay)
        print()
    
    @staticmethod
    def blink(text: str, times: int = 3, delay: float = 0.3):
        """闪烁效果"""
        for _ in range(times):
            print(f"\r{text}", end='')
            sys.stdout.flush()
            time.sleep(delay)
            print(f"\r{' ' * len(text)}", end='')
            sys.stdout.flush()
            time.sleep(delay)
        print(f"\r{text}")


# 便捷函数
def show_progress(message: str, current: int, total: int):
    """显示进度"""
    percent = (current / total) * 100
    bar_length = 30
    filled = int(bar_length * percent / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    print(f"\r{CliColors.CYAN}{message} [{bar}] {percent:.1f}%{CliColors.ENDC}", end='')
    sys.stdout.flush()


def show_table(headers: List[str], data: List[List[Any]]):
    """显示表格"""
    table = Table(headers, data)
    table.render()


def show_card(title: str, content: str):
    """显示卡片"""
    card = Card(title, content)
    card.render()


def show_tree(data: Dict[str, Any]):
    """显示树形结构"""
    tree = Tree(data)
    tree.render()


def show_menu(title: str, items: List[Dict[str, Any]]) -> str:
    """显示菜单"""
    menu = Menu(title, items)
    return menu.show()