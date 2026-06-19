#!/usr/bin/env python3
"""简单的Python脚本"""

def fibonacci(n):
    """计算斐波那契数列"""
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

if __name__ == "__main__":
    # 计算前10项
    for i in range(10):
        print(f"fibonacci({i}) = {fibonacci(i)}")
