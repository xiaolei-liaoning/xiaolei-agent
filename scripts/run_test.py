#!/usr/bin/env python3
import asyncio
import time
from skills.deep_thinking.handler import DeepThinkingHandler

async def test():
    queries = [
        "深度分析AI",
        "深度研究量子",
        "深度思考教育",
        "深度分析气候变化",
        "深度思考教育改革",
        "深度研究区块链",
        "深度分析数字化",
        "深度思考新能源",
        "深度研究智慧城市",
        "深度分析人工智能"
    ]

    results = []
    start_total = time.time()

    for i, q in enumerate(queries):
        print(f"[{i+1}/10] {q}...", end=" ", flush=True)
        h = DeepThinkingHandler()
        s = time.time()
        try:
            r = await h.execute(query=q)
            e = time.time() - s
            success = r.get("success", False)
            print(f"{'✅' if success else '❌'} {e:.1f}s")
            results.append({"id": i+1, "elapsed": e, "success": success})
        except Exception as ex:
            e = time.time() - s
            print(f"❌ {e:.1f}s - {ex}")
            results.append({"id": i+1, "elapsed": e, "success": False})

    total = time.time() - start_total
    print(f"\n总耗时: {total:.1f}秒")
    success_count = sum(1 for r in results if r["success"])
    print(f"成功: {success_count}/{len(results)}")
    elapsed = [r["elapsed"] for r in results if r["success"]]
    if elapsed:
        print(f"平均: {sum(elapsed)/len(elapsed):.1f}s | 最快: {min(elapsed):.1f}s | 最慢: {max(elapsed):.1f}s")
        print(f"QPS: {len(elapsed)/total:.2f} 请求/秒")

if __name__ == "__main__":
    asyncio.run(test())
