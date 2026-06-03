"""CLI分页显示模块 - 简洁的步骤展示"""

from typing import List, Dict, Optional
from cli.colors import CliColors, print_color


class StepDisplay:
    """步骤显示组件"""
    
    def __init__(self, steps: List[Dict], items_per_page: int = 3):
        """
        初始化步骤显示
        
        Args:
            steps: 步骤列表，每个步骤包含 title, description
            items_per_page: 每页显示的步骤数
        """
        self.steps = steps
        self.items_per_page = items_per_page
        self.current_page = 1
        self.current_step = 0
        self.step_status = ['pending'] * len(steps)  # pending, active, success, failed
        
    @property
    def total_pages(self) -> int:
        """计算总页数"""
        return (len(self.steps) + self.items_per_page - 1) // self.items_per_page
    
    @property
    def current_steps(self) -> List[Dict]:
        """获取当前页的步骤"""
        start = (self.current_page - 1) * self.items_per_page
        end = start + self.items_per_page
        return self.steps[start:end]
    
    @property
    def current_page_indices(self) -> List[int]:
        """获取当前页步骤的原始索引"""
        start = (self.current_page - 1) * self.items_per_page
        end = start + self.items_per_page
        return list(range(start, min(end, len(self.steps))))
    
    def set_step_active(self, step_index: int):
        """设置步骤为活跃状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'active'
            self.current_step = step_index
    
    def set_step_success(self, step_index: int):
        """设置步骤为成功状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'success'
    
    def set_step_failed(self, step_index: int):
        """设置步骤为失败状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'failed'
    
    def set_step_skipped(self, step_index: int):
        """设置步骤为跳过状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'skipped'
    
    def get_status_icon(self, status: str) -> str:
        """获取状态图标"""
        icons = {
            'pending': '○',
            'active': '●',
            'success': '✓',
            'failed': '✗'
        }
        return icons.get(status, '○')
    
    def get_status_color(self, status: str) -> str:
        """获取状态颜色"""
        colors = {
            'pending': CliColors.GRAY,
            'active': CliColors.CYAN,
            'success': CliColors.GREEN,
            'failed': CliColors.RED
        }
        return colors.get(status, CliColors.GRAY)
    
    def display_header(self):
        """显示头部信息"""
        print_color(f"\n┌─────────────────────────────────────────────────────────────", CliColors.GRAY)
        print_color(f"│  🤔 智能任务处理", CliColors.BRIGHT_BLUE + CliColors.BOLD)
        print_color(f"└─────────────────────────────────────────────────────────────", CliColors.GRAY)
    
    def display_steps(self):
        """显示当前页的步骤"""
        current_indices = self.current_page_indices
        
        for i, step_idx in enumerate(current_indices):
            step = self.steps[step_idx]
            status = self.step_status[step_idx]
            icon = self.get_status_icon(status)
            color = self.get_status_color(status)
            
            step_num = step_idx + 1
            print()
            print_color(f"  [{step_num}/{len(self.steps)}] {icon} {step['title']}", color)
            
            if status == 'active':
                print_color(f"      → {step['description']}", CliColors.WHITE)
    
    def display_pagination(self):
        """显示分页导航"""
        if self.total_pages <= 1:
            return
        
        print()
        print_color("  ─────────────────────────────────────────────────────────────", CliColors.GRAY)
        
        nav_items = []
        
        # 上一页
        if self.current_page > 1:
            nav_items.append(f"[{CliColors.GREEN}◀{CliColors.ENDC}]")
        else:
            nav_items.append("[◀]")
        
        # 页码
        for page in range(1, self.total_pages + 1):
            if page == self.current_page:
                nav_items.append(f"{CliColors.CYAN + CliColors.BOLD}{page}{CliColors.ENDC}")
            else:
                nav_items.append(str(page))
        
        # 下一页
        if self.current_page < self.total_pages:
            nav_items.append(f"[{CliColors.GREEN}▶{CliColors.ENDC}]")
        else:
            nav_items.append("[▶]")
        
        print_color(f"  {' '.join(nav_items)}", CliColors.GRAY)
    
    def display_progress(self):
        """显示进度条"""
        completed = sum(1 for s in self.step_status if s == 'success')
        total = len(self.steps)
        progress = int((completed / total) * 20)
        
        print()
        print_color(f"  Progress: [{CliColors.GREEN}{'█' * progress}{CliColors.GRAY}{'░' * (20 - progress)}{CliColors.ENDC}] {completed}/{total}", CliColors.WHITE)
    
    def display(self):
        """完整显示"""
        self.display_header()
        self.display_steps()
        self.display_pagination()
        self.display_progress()
    
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1


class SimpleStepDisplay:
    """简洁版步骤显示"""
    
    def __init__(self, steps: List[Dict]):
        self.steps = steps
        self.current_step = 0
        self.step_status = ['pending'] * len(steps)
    
    def set_step_active(self, step_index: int):
        """设置步骤为活跃状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'active'
            self.current_step = step_index
    
    def set_step_success(self, step_index: int):
        """设置步骤为成功状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'success'
    
    def set_step_failed(self, step_index: int):
        """设置步骤为失败状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'failed'
    
    def set_step_skipped(self, step_index: int):
        """设置步骤为跳过状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'skipped'
    
    def display(self):
        """显示步骤进度"""
        print()
        print_color("┌─────────────────────────────────────────────────────────────", CliColors.GRAY)
        
        for i, step in enumerate(self.steps):
            status = self.step_status[i]
            
            if status == 'success':
                print_color(f"│ ✅ [{i+1}/{len(self.steps)}] {step['title']}", CliColors.GREEN)
            elif status == 'active':
                print_color(f"│ 🔄 [{i+1}/{len(self.steps)}] {step['title']}", CliColors.CYAN)
                print_color(f"│      → {step['description']}", CliColors.WHITE)
            elif status == 'failed':
                print_color(f"│ ❌ [{i+1}/{len(self.steps)}] {step['title']}", CliColors.RED)
            else:
                print_color(f"│ ○ [{i+1}/{len(self.steps)}] {step['title']}", CliColors.GRAY)
        
        print_color("└─────────────────────────────────────────────────────────────", CliColors.GRAY)
        print()


# ANSI 转义码（用于直接终端输出，无需 Rich 解析）
_ANSI = {
    'green': '\033[38;2;78;186;101m',
    'cyan': '\033[38;2;0;255;255m',
    'gray': '\033[38;2;153;153;153m',
    'red': '\033[38;2;255;107;128m',
    'end': '\033[0m',
}


class CompactStepDisplay:
    """紧凑版步骤显示 - 一行显示所有步骤"""

    def __init__(self, steps: List[Dict]):
        self.steps = steps
        self.step_status = ['pending'] * len(steps)
        self.last_length = 0

    def set_step_active(self, step_index: int):
        """设置步骤为活跃状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'active'

    def set_step_success(self, step_index: int):
        """设置步骤为成功状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'success'

    def set_step_failed(self, step_index: int):
        """设置步骤为失败状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'failed'

    def set_step_skipped(self, step_index: int):
        """设置步骤为跳过状态"""
        if 0 <= step_index < len(self.step_status):
            self.step_status[step_index] = 'skipped'

    def display(self):
        """显示步骤进度（一行显示）"""
        import sys
        a = _ANSI

        # 构建步骤状态显示
        step_display = ""
        for i, step in enumerate(self.steps):
            status = self.step_status[i]

            if status == 'success':
                step_display += f"{a['green']}【✓】{step['title']}{a['end']}"
            elif status == 'active':
                step_display += f"{a['cyan']}【●】{step['title']}{a['end']}"
            elif status == 'failed':
                step_display += f"{a['red']}【✗】{step['title']}{a['end']}"
            elif status == 'skipped':
                step_display += f"{a['gray']}【○】{step['title']}{a['end']}"
            else:
                step_display += f"{a['gray']}【 】{step['title']}{a['end']}"

            if i < len(self.steps) - 1:
                step_display += " → "

        # 计算进度
        completed = sum(1 for s in self.step_status if s == 'success')
        total = len(self.steps)
        percent = int((completed / total) * 100)

        # 构建进度条
        bar_width = 30
        filled = int((completed / total) * bar_width)
        progress_bar = f"{a['cyan']}[{a['green']}{'█' * filled}{a['gray']}{'░' * (bar_width - filled)}{a['cyan']}]{a['end']} {percent}%"

        # 构建完整输出
        full_output = f"{step_display}  {progress_bar}"

        # 用空格清除之前的输出
        if self.last_length > len(full_output):
            full_output += " " * (self.last_length - len(full_output))

        self.last_length = len(full_output)

        # 输出到同一行
        sys.stdout.write(f"\r{full_output}")
        sys.stdout.flush()