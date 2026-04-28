"""
开发模式启动器 - 支持代码修改自动重启（热重载）
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class CodeChangeHandler(FileSystemEventHandler):
    """代码变化处理器"""
    
    def __init__(self, restart_callback, watch_dirs=None):
        super().__init__()
        self.restart_callback = restart_callback
        self.watch_dirs = watch_dirs or ['.']
        self.last_restart = 0
        self.cooldown = 2  # 冷却时间（秒），避免频繁重启
    
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return
        
        # 只监控Python文件
        if not event.src_path.endswith('.py'):
            return
        
        # 检查冷却时间
        current_time = time.time()
        if current_time - self.last_restart < self.cooldown:
            return
        
        print(f"\n📝 检测到代码变化: {event.src_path}")
        print("🔄 正在重启服务...")
        
        self.last_restart = current_time
        self.restart_callback()


class DevServer:
    """开发服务器"""
    
    def __init__(self, main_module: str = "main.py", port: int = 8001):
        self.main_module = main_module
        self.port = port
        self.process = None
        self.observer = None
        self.watch_dirs = ['core', 'skills', 'tools']
    
    def start_process(self):
        """启动主进程"""
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'  # 无缓冲输出
        
        self.process = subprocess.Popen(
            [sys.executable, self.main_module],
            env=env,
            cwd=os.getcwd()
        )
        print(f"✅ 服务已启动 (PID: {self.process.pid})")
    
    def stop_process(self):
        """停止主进程"""
        if self.process:
            print("⏹️  正在停止服务...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            print("✅ 服务已停止")
    
    def restart_process(self):
        """重启主进程"""
        self.stop_process()
        time.sleep(1)
        self.start_process()
    
    def setup_file_watcher(self):
        """设置文件监听器"""
        handler = CodeChangeHandler(
            restart_callback=self.restart_process,
            watch_dirs=self.watch_dirs
        )
        
        self.observer = Observer()
        
        for watch_dir in self.watch_dirs:
            path = Path(watch_dir)
            if path.exists():
                self.observer.schedule(handler, str(path), recursive=True)
                print(f"👁️  监听目录: {watch_dir}/")
        
        self.observer.start()
        print("✅ 文件监听器已启动")
    
    def stop_file_watcher(self):
        """停止文件监听器"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            print("✅ 文件监听器已停止")
    
    def run(self):
        """运行开发服务器"""
        print("\n" + "="*60)
        print("🚀 开发模式启动")
        print("="*60)
        print(f"📍 主模块: {self.main_module}")
        print(f"🌐 端口: {self.port}")
        print(f"👁️  监听目录: {', '.join(self.watch_dirs)}")
        print("="*60)
        print("\n💡 提示:")
        print("   - 修改代码后会自动重启")
        print("   - 按 Ctrl+C 停止服务")
        print("="*60 + "\n")
        
        try:
            # 启动文件监听
            self.setup_file_watcher()
            
            # 启动主进程
            self.start_process()
            
            # 等待进程结束
            self.process.wait()
            
        except KeyboardInterrupt:
            print("\n\n⏹️  收到中断信号，正在关闭...")
        finally:
            # 清理资源
            self.stop_process()
            self.stop_file_watcher()
            print("\n✅ 开发服务器已关闭")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='开发模式启动器')
    parser.add_argument('--module', default='main.py', help='主模块文件')
    parser.add_argument('--port', type=int, default=8001, help='服务端口')
    parser.add_argument('--watch', nargs='+', default=['core', 'skills', 'tools'],
                       help='监听的目录列表')
    
    args = parser.parse_args()
    
    server = DevServer(main_module=args.module, port=args.port)
    server.watch_dirs = args.watch
    server.run()
