#!/usr/bin/env python3
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp._impl.deep_thinking.handler import DeepThinkingHandler

queries = [
    "深度分析人工智能对医疗的影响",
    "深度研究量子计算的最新进展",
    "深度分析如何应对气候变化",
    "深度思考教育改革的未来",
    "深度分析数字化转型策略",
    "深度研究区块链技术应用",
    "深度分析企业数字化转型",
    "深度思考新能源汽车发展",
    "深度研究如何构建智慧城市",
    "深度分析人工智能在金融的应用"
]

async def single_request(q, idx):
    print(f"[{idx}] {q[:30]}...", end=" ", flush=True)
    h = DeepThinkingHandler()
    s = time.time()
    try:
        r = await h.execute(query=q)
        e = time.time() - s
        print(f"✅ {e:.1f}s")
        return {"id": idx, "elapsed": e, "success": True}
    except Exception as ex:
        e = time.time() - s
        print(f"❌ {ex}")
        return {"id": idx, "elapsed": e, "success": False, "error": str(ex)}

async def test_concurrent_10():
    print("\n" + "="*60)
    print("🚀 10个并发深度思考测试")
    print("="*60)

    start_total = time.time()

    tasks = [single_request(queries[i], i+1) for i in range(10)]
    results = await asyncio.gather(*tasks)

    total = time.time() - start_total

    print(f"\n总耗时: {total:.1f}秒")
    success = sum(1 for r in results if r["success"])
    print(f"成功: {success}/{len(results)}")

    elapsed = [r["elapsed"] for r in results if r["success"]]
    if elapsed:
        print(f"平均: {sum(elapsed)/len(elapsed):.1f}s | 最快: {min(elapsed):.1f}s | 最慢: {max(elapsed):.1f}s")
        print(f"QPS: {len(elapsed)/total:.2f} 请求/秒")

async def test_3_concurrent():
    print("\n" + "="*60)
    print("🚀 3轮并发测试 (每轮3个请求)")
    print("="*60)

    all_results = []
    total_start = time.time()

    for round_num in range(3):
        print(f"\n--- 第{round_num+1}轮 ---")
        start = time.time()
        tasks = [single_request(queries[i % 10], i+1) for i in range(3)]
        results = await asyncio.gather(*tasks)
        round_time = time.time() - start
        all_results.extend(results)
        print(f"第{round_num+1}轮耗时: {round_time:.1f}秒")

    total = time.time() - total_start
    success = sum(1 for r in all_results if r["success"])
    print(f"\n总耗时: {total:.1f}秒")
    print(f"成功: {success}/{len(all_results)}")
    elapsed = [r["elapsed"] for r in all_results if r["success"]]
    if elapsed:
        print(f"平均: {sum(elapsed)/len(elapsed):.1f}s | 最快: {min(elapsed):.1f}s | 最慢: {max(elapsed):.1f}s")
        print(f"QPS: {len(elapsed)/total:.2f} 请求/秒")

async def main():
    await test_concurrent_10()
    await test_3_concurrent()
    print("\n" + "="*60)
    print("🎉 压力测试完成!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
