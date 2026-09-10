"""
测试 _llm_write_workflow prompt 稳定性 — pytest 化（2026-09-10）

原为脚本型 main，现 pytest 收集。需要真实 LLM 评分，默认跳过:
  XIAOLEI_REAL_LLM=1 python -m pytest tests/test_llm_workflow_prompt.py
"""

import asyncio
import json
import os
import re
import sys
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [pytest.mark.asyncio, pytest.mark.real_llm]

from core.engine.llm_backend import get_llm_router


TEST_TASKS = [
    {
        "name": "代码-写个游戏",
        "task": "用 Python 写一个贪吃蛇游戏，放到 ~/Desktop/snake.py",
        "expect_template": "dag",
    },
    {
        "name": "代码-重构模块",
        "task": "重构 core/handlers/ 目录下的 chat_handler.py，拆成多个小文件",
        "expect_template": "dag",
    },
    {
        "name": "搜索-多平台对比",
        "task": "搜索百度热搜、微博热搜、知乎热榜，对比分析三者的热点的异同，输出对比报告到 report.md",
        "expect_template": "rules",
    },
    {
        "name": "流程-数据流水线",
        "task": "从美团爬取餐厅数据，清洗数据，分析最受欢迎的菜系，生成分析图表",
        "expect_template": "rules",
    },
    {
        "name": "决策-动态判断",
        "task": "检查系统当前运行的进程，如果 CPU 占用超过 80% 就分析高占用进程并给出优化建议，否则生成系统健康报告",
        "expect_template": "rules",
    },
    {
        "name": "动态-批量处理",
        "task": "扫描当前目录下所有 .py 文件，对每个文件进行 code review 并输出 review 报告",
        "expect_template": "rules",
    },
    {
        "name": "混合-综合任务",
        "task": "搜索最近的 AI 新闻，然后根据新闻内容写一篇摘要博客，最后发布到我的博客网站",
        "expect_template": "rules",
    },
]


def check_syntax(script: str) -> list:
    """检查生成的 JS 脚本的基本语法问题"""
    issues = []

    if "export const meta" not in script:
        issues.append("缺少 export const meta")
    if "export default async function" not in script:
        issues.append("缺少 export default async function")

    # parallel 里不应该有 await agent() 直接调用（应该包在 thunk 里）
    parallel_wrong_await = re.findall(
        r"parallel\([^)]*await agent\(", script, re.DOTALL
    )
    if parallel_wrong_await:
        issues.append(f"parallel 里发现了 await agent() 的直接调用（需要包在 thunk 里）: {len(parallel_wrong_await)} 处")

    return issues


def analyze_pattern_usage(script: str) -> dict:
    """分析脚本中使用了哪些编排模式"""
    patterns = {
        "parallel": "parallel(" in script,
        "dag": "$dag(" in script,
        "serial_agent": "await agent(" in script,
        "phase": "phase(" in script,
        "log": "log(" in script,
        "if_else": bool(re.search(r"\bif\s*\(.*?\)", script)),
        "for_loop": bool(re.search(r"\bfor\s*\(", script)),
    }
    return patterns


def score_task_fit(expect_template: str, patterns: dict) -> tuple:
    """评估模式选择是否适合"""
    if expect_template == "dag":
        if patterns["dag"]:
            return (5, "✅ 正确使用 $dag 模式（代码类任务的标准模板）")
        else:
            return (3, "⚠️ 预期用 $dag 但实际用了其他模式")
    else:
        # rules 类：评估模式是否合适
        used_count = sum(1 for v in patterns.values() if v)
        has_combination = patterns["parallel"] and patterns["serial_agent"]
        # 纯串行流水线（搜索→分析→写报告）——正确但简单
        is_serial_flow = patterns["serial_agent"] and not patterns["parallel"] and not patterns["dag"]

        if used_count >= 3 and has_combination:
            return (5, f"✅ 综合运用 {used_count} 种模式，有 parallel+串行组合")
        elif used_count >= 2 and has_combination:
            return (4, f"👍 用了 {used_count} 种模式，有 parallel+串行组合")
        elif is_serial_flow and patterns["phase"]:
            return (4, f"👍 串行流水线 + 阶段分组，符合任务的依赖关系")
        elif is_serial_flow:
            return (3, f"↗️ 串行流水线，模式选择正确但可以加 phase() 分组")
        elif used_count >= 2:
            return (3, f"⚠️ 用了 {used_count} 种模式，但缺少 parallel+串行组合")
        else:
            return (2, f"⚠️ 只用了 {used_count} 种模式，编排过于简单")


async def run_test_real_llm():
    """原脚本入口 — pytest 化后作为 async 测试入口（XIAOLEI_REAL_LLM=1 才跑）"""
    router = get_llm_router()
    if not router or not router.is_available():
        pytest.skip("LLM Router 不可用，跳过此真实 LLM 测试")
        return

    from cli.handlers.chat_handler import ChatHandler
    chat_handler = ChatHandler(None)

    results = []

    for i, tc in enumerate(TEST_TASKS):
        print(f"\n{'='*60}")
        print(f"测试 {i+1}/{len(TEST_TASKS)}: {tc['name']}")
        print(f"任务: {textwrap.shorten(tc['task'], width=80)}")
        print(f"{'='*60}")

        # 检测代码任务分类——与 _llm_write_workflow 保持同步
        task_lower = tc["task"][:200].lower()
        code_keywords = [
            "写代码", "写程序", "写脚本", "写一个", "写个",
            "实现", "创建", "项目", "模块", "重构", "拆分",
            "生成代码", "代码生成", "开发",
            "generat", "implement", "create", "refactor", "build",
        ]
        code_antitrigger = ["写一篇", "写博客", "写文章", "写报告", "写文档"]
        detected_code = (
            any(kw in task_lower for kw in code_keywords)
            and not any(kw in task_lower for kw in code_antitrigger)
        )
        print(f"  代码任务检测: {'是' if detected_code else '否'}")

        # 生成 workflow 脚本
        script = await chat_handler._llm_write_workflow(tc["task"])

        if not script:
            print(f"  ❌ LLM 没有返回有效脚本")
            results.append({"name": tc["name"], "status": "FAIL", "reason": "脚本为空"})
            continue

        # 显示前 600 字符
        print(f"\n  生成脚本:\n{script[:600]}")
        if len(script) > 600:
            print(f"  ... (共 {len(script)} 字符)")

        # 语法检查
        issues = check_syntax(script)
        if issues:
            print(f"\n  ⚠️ 语法问题:")
            for iss in issues:
                print(f"    - {iss}")

        # 模式分析
        patterns = analyze_pattern_usage(script)
        used = [k for k, v in patterns.items() if v]
        print(f"\n  使用模式: {', '.join(used)}")

        score, comment = score_task_fit(tc["expect_template"], patterns)
        status = "PASS" if score >= 4 else ("WARN" if score >= 2 else "FAIL")
        print(f"  评分: {score}/5 — {comment}")
        print(f"  状态: {status}")

        results.append({
            "name": tc["name"],
            "status": status,
            "score": score,
            "comment": comment,
            "patterns": used,
            "script_length": len(script),
            "issues": issues,
        })

        await asyncio.sleep(2)

    # ── 汇总 ──
    print(f"\n\n{'='*60}")
    print("📊 测试汇总")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"  通过: {passed}/{len(results)} | 警告: {warned} | 失败: {failed}")
    print()
    for r in results:
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[r["status"]]
        patterns_str = ", ".join(r["patterns"])
        print(f"  {icon} {r['name']} ({r['score']}/5) [{patterns_str}]")
        if r.get("issues"):
            for i in r["issues"]:
                print(f"      问题: {i}")

    return results


@pytest.mark.real_llm
async def test_llm_workflow_prompt_stability():
    """pytest 收集入口：真实 LLM 调 _llm_write_workflow 生成 workflow 脚本"""
    results = await run_test_real_llm()
    # 断言核心 — 非 FAIL 数量大于 0（WARN 视为容忍，全 FAIL 才算挂）
    if results:
        fails = [r for r in results if r["status"] == "FAIL"]
        assert len(fails) < len(results), f"全部 {len(results)} 个用例 FAIL，prompt 质量崩塌"


if __name__ == "__main__":
    asyncio.run(run_test_real_llm())
