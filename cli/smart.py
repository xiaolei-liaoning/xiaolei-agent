"""CLI智能工作流模块"""

from pathlib import Path
import json

from cli.colors import print_header, print_error, print_success, print_warning, print_info
from cli.base import WorkflowEngineWrapper, display_workflow_result


async def handle_smart(args):
    """处理智能工作流命令"""
    print_header("智能工作流执行")

    if not args.request:
        print_error("请提供用户请求")
        return

    wrapper = WorkflowEngineWrapper()
    result = await wrapper.create_and_execute(args.request)

    await display_workflow_result(result)


async def handle_workflow_run(args):
    """处理工作流运行命令"""
    print_header("执行工作流文件")

    if not args.file:
        print_error("请提供工作流文件路径")
        return

    wrapper = WorkflowEngineWrapper()
    result = await wrapper.execute_workflow_file(args.file)

    await display_workflow_result(result)


async def handle_workflow_list(args):
    """列出可用工作流模板"""
    print_header("工作流模板列表")

    workflows_dir = Path(__file__).resolve().parent.parent / "skills" / "workflows"
    if workflows_dir.exists():
        for item in workflows_dir.rglob("*.json"):
            rel_path = item.relative_to(workflows_dir)
            print(f"  • {rel_path}")
    else:
        print_warning("工作流目录不存在")


async def handle_workflow_save(args):
    """保存工作流到文件"""
    print_header("保存工作流")

    if not args.request:
        print_error("请提供用户请求")
        return

    wrapper = WorkflowEngineWrapper()
    engine = wrapper.get_engine()

    result = await engine.create_smart_workflow(args.request)
    if not result.get("success"):
        print_error(result.get("error", "创建失败"))
        return

    workflow = result["workflow"]

    filename = args.output or f"workflow_{workflow['name']}.json"
    filepath = Path(filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    print_success(f"工作流已保存到: {filepath.absolute()}")
