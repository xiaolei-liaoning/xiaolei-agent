"""深度测试：模板嵌套 + 链式执行 + MCP + Arbor"""
import sys, os, json, time, asyncio, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS = Path.home() / "Desktop/v2-deep-test-results"
RESULTS.mkdir(parents=True, exist_ok=True)
LOG = open(RESULTS / "deep_test_log.txt", "w", encoding="utf-8")
all_results = []

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line); LOG.write(line + "\n"); LOG.flush()

def ok(r): return {"name":r[0],"success":r[1],"elapsed":round(r[2],1),"attempts":r[3]}
def _save():
    with open(RESULTS / "deep_test_results.json", "w", encoding="utf-8") as f:
        json.dump({"results":all_results,"summary":{"total":len(all_results),"passed":sum(1 for r in all_results if r["success"])},"finished_at":datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)

# ================================================
# PART 1: 模板嵌套 (workflow() 调用子工作流)
# ================================================
async def test_nesting():
    from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow, WorkflowConfig
    log("\n═══ PART 1: 模板嵌套 ═══")
    script = (Path(__file__).parent / "nest_parent.js").read_text()
    for attempt in range(2):
        start = time.time()
        try:
            runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=150, budget_total=500_000, resume_cache=False))
            result = await asyncio.wait_for(runtime.run(script, args={"test": True}), timeout=180)
            el = time.time() - start
            ok = result.success if hasattr(result,'success') else bool(result)
            log(f"  {'✅' if ok else '❌'} 模板嵌套: {el:.1f}s{' (重试)' if attempt else ''}")
            return ("模板嵌套(workflow嵌套)", ok, el, attempt+1)
        except Exception as e:
            el = time.time() - start
            if attempt == 0: log(f"  ⚠️ 模板嵌套: {str(e)[:60]}, 重试..."); continue
            log(f"  ❌ 模板嵌套: {str(e)[:80]}")
            return ("模板嵌套(workflow嵌套)", False, el, attempt+1)

# ================================================
# PART 2: 自定义 JS 链式执行
# ================================================
async def test_chain():
    from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow, WorkflowConfig
    log("\n═══ PART 2: 链式执行 (自定义 .js) ═══")
    script = (Path(__file__).parent / "chain_runner.js").read_text()
    for attempt in range(2):
        start = time.time()
        try:
            runtime = ClaudeCodeWorkflow(WorkflowConfig(timeout=180, budget_total=500_000, resume_cache=False))
            result = await asyncio.wait_for(runtime.run(script), timeout=210)
            el = time.time() - start
            ok = result.success if hasattr(result,'success') else bool(result)
            log(f"  {'✅' if ok else '❌'} 链式执行: {el:.1f}s")
            return ("链式执行(串行 .js 模板)", ok, el, attempt+1)
        except Exception as e:
            el = time.time() - start
            if attempt == 0: log(f"  ⚠️ 链式执行: {str(e)[:60]}, 重试..."); continue
            log(f"  ❌ 链式执行: {str(e)[:80]}")
            return ("链式执行(串行 .js 模板)", False, el, attempt+1)

# ================================================
# PART 3: 深度 MCP 任务
# ================================================
PYTHON = sys.executable
CLI_DIR = str(Path(__file__).parent.parent)

def run_cli(cmd, timeout=240):
    start = time.time()
    try:
        proc = subprocess.Popen(
            [PYTHON, "cli.py", cmd], cwd=CLI_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        el = round(time.time()-start, 1)
        return {"success": proc.returncode==0, "elapsed": el, "stdout": stdout[-800:], "stderr": stderr[-400:]}
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait()
        return {"success": False, "elapsed": round(time.time()-start,1), "stdout": "", "stderr": "TIMEOUT"}
    except Exception as e:
        return {"success": False, "elapsed": round(time.time()-start,1), "stdout": "", "stderr": str(e)[:300]}

def test_mcp(name, cmd, timeout=180, desk_kw=None):
    desk_kw = desk_kw or []
    log(f"\n  MCP 测试: {name}")
    for attempt in range(2):
        r = run_cli(cmd, timeout)
        desk_files = [str(p.name) for p in Path.home().joinpath("Desktop").iterdir() if any(k in p.name for k in desk_kw)] if desk_kw else []
        ok = r['success'] and (bool(desk_files) if desk_kw else True)
        log(f"  {'✅' if ok else '❌'} {name}: {r['elapsed']}s{'  files: '+str(desk_files) if desk_files else ''}")
        if ok or attempt==1: break
        log(f"  ⚠️ 重试...")
    all_results.append({"name":"MCP-"+name,"success":ok,"elapsed":r['elapsed'],"attempts":attempt+1})

async def test_mcp_tasks():
    log("\n═══ PART 3: 深度 MCP 任务 ═══")
    test_mcp("playwright-form", '使用playwright打开https://www.baidu.com，搜索opencli，截图保存到桌面', 180, ["baidu","screenshot","截图"])
    test_mcp("codegraph-scan", '使用 codegraph 分析 /Users/leiyuxuan/Desktop/小雷版agent 的项目结构，列出所有顶级模块和依赖关系，保存到桌面', 240, ["codegraph","结构","依赖","模块"])
    test_mcp("playwright-multistep", '使用playwright打开百度搜索"Python 异步编程"，提取前3条搜索结果的大标题和链接，保存到桌面', 120, ["baidu","search","异步","Python"])

# ================================================
# MAIN
# ================================================
async def main():
    log("="*50)
    log("深度测试：模板嵌套 + 链式执行 + MCP")
    log("="*50)
    log(f"开始时间: {datetime.now().isoformat()}")

    # Part 1+2: JS 工作流
    log("\n--- JS 工作流深度测试 ---")
    r1 = await test_nesting()
    all_results.append(ok(r1))
    r2 = await test_chain()
    all_results.append(ok(r2))

    # Part 3: MCP 深度任务
    await test_mcp_tasks()

    _save()
    # 汇总
    passed = sum(1 for r in all_results if r["success"])
    log(f"\n{'='*50}")
    log(f"深度测试结果: {passed}/{len(all_results)} passed")
    for r in all_results:
        icon = '✅' if r['success'] else '❌'
        log(f"  {icon} {r['name']}: {r['elapsed']}s (attempts={r['attempts']})")

    report = {"results": all_results, "summary": {"total": len(all_results), "passed": passed}, "finished_at": datetime.now().isoformat()}
    (RESULTS / "deep_test_results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"\n📊 结果: {RESULTS / 'deep_test_results.json'}")
    LOG.close()

if __name__ == "__main__":
    asyncio.run(main())
