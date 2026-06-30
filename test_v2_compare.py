"""V2 架构对比：单 Agent vs JS 多 Agent 能力差距测试"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

RESULTS = []

async def run_single_agent(task: str, label: str):
    """通过 CLI 单 Agent 模式执行"""
    print(f"\n{'='*60}")
    print(f"[单Agent] {label}: {task}")
    print(f"{'='*60}")
    start = time.time()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "cli.cli", task,
        cwd=Path(__file__).parent,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    elapsed = time.time() - start
    text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")

    # 提取关键指标
    success = "✅" in text or "成功" in text[-500:]
    rounds = 0
    for line in text.split("\n"):
        if "━━━ 第" in line:
            rounds += 1

    RESULTS.append({
        "mode": "single",
        "label": label,
        "task": task,
        "time": round(elapsed, 1),
        "success": success,
        "rounds": rounds,
        "output_len": len(text),
        "errors": [l for l in err_text.split("\n") if "ERROR" in l or "WARNING" in l],
    })
    print(f"  ⏱ {elapsed:.1f}s | rounds={rounds} | success={success} | output={len(text)}chars")
    return text

async def run_multi_agent(task: str, label: str):
    """通过 CLI /orchestrate 多 Agent JS Workflow 模式执行"""
    print(f"\n{'='*60}")
    print(f"[多Agent] {label}: {task}")
    print(f"{'='*60}")
    start = time.time()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "cli.cli", "/orchestrate", task,
        cwd=Path(__file__).parent,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    elapsed = time.time() - start
    text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")

    success = "✅" in text or "成功" in text[-500:]
    agents_used = text.count("__IPC__") if "__IPC__" in text else 0

    RESULTS.append({
        "mode": "multi",
        "label": label,
        "task": task,
        "time": round(elapsed, 1),
        "success": success,
        "agents_used": agents_used,
        "output_len": len(text),
        "errors": [l for l in err_text.split("\n") if "ERROR" in l or "WARNING" in l],
    })
    print(f"  ⏱ {elapsed:.1f}s | agents={agents_used} | success={success} | output={len(text)}chars")
    return text

async def main():
    tests = [
        ("搜索百度热搜", "simple_search"),
        ("分析 opencode_副本 项目的技术栈和架构", "analysis"),
    ]

    for task, label in tests:
        # 单 Agent
        t1 = await run_single_agent(task, label)

        # 多 Agent
        t2 = await run_multi_agent(task, label)

    # 输出对比表
    print(f"\n\n{'='*70}")
    print("V2 架构对比结果")
    print(f"{'='*70}")
    print(f"{'场景':<20} {'模式':<8} {'耗时(s)':<10} {'成功':<8} {'轮次/Agent':<12} {'输出(字符)':<12}")
    print("-"*70)
    for r in RESULTS:
        extra = str(r.get("rounds", r.get("agents_used", "?")))
        print(f"{r['label']:<20} {r['mode']:<8} {r['time']:<10} {str(r['success']):<8} {extra:<12} {r['output_len']:<12}")
    print("-"*70)

    # 保存结果
    (Path(__file__).parent / "test_v2_compare_results.json").write_text(
        json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n结果已保存: test_v2_compare_results.json")

if __name__ == "__main__":
    asyncio.run(main())
