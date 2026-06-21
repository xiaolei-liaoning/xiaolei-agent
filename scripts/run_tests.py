#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

def main():
    print("=== 开始运行测试 ===")
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_handlers.py",
        "tests/test_multi_agent_system.py",
        "tests/test_api_routes.py",
        "tests/test_skills.py",
        "tests/test_tools.py",
        "-v", "--tb=short"
    ]
    
    result = subprocess.run(cmd, cwd=str(Path(__file__).parent), capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("\nSTDERR:")
        print(result.stderr)
    
    print(f"\n退出码: {result.returncode}")
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())