#!/usr/bin/env python3
import asyncio
import time
from skills.deep_thinking.handler import DeepThinkingHandler

queries = [
    "深度分析AI对医疗",
    "深度研究量子计算",
    "深度思考教育改革",
]

async def single(q, i):
    h = DeepThinkingHandler()
    s = time.time()
    r = await h.execute(query=q)
    e = time.time() - s
    print(f"[{i}] ✅ {e:.1f}s")
    return e

async def main():
    print("="*50)
    print("🚀 3个并发深度思考测试")
    print("="*50)
    start = time.time()
    tasks = [single(queries[i], i+1) for i in range(3)]
    results = await asyncio.gather(*tasks)
    total = time.time() - start
    print(f"\n总耗时: {total:.1f}秒")
    print(f"成功: {len(results)}/3")
    print(f"QPS: {3/total:.2f} 请求/秒")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
