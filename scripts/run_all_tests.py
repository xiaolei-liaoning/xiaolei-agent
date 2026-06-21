#!/usr/bin/env python3
"""统一运行所有测试脚本"""

import sys
import os
import asyncio
import time
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数 - 运行所有测试"""
    
    all_tests = [
        ("深度思考+RAG+BFS测试", "test_deep_thinking_rag_bfs.py"),
        ("多Agent协作与并发测试", "test_multi_agent_concurrent.py"),
        ("压力测试与缓存优化", "test_stress_cache.py"),
        ("技能注册与测试", "test_skill_registration.py"),
    ]
    
    total_start = time.time()
    results = {}
    
    logger.info("=" * 80)
    logger.info("开始运行所有测试")
    logger.info("=" * 80)
    
    for test_name, test_file in all_tests:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"运行: {test_name}")
        logger.info(f"{'=' * 80}")
        
        test_path = Path(__file__).parent / test_file
        
        if not test_path.exists():
            logger.error(f"❌ 测试文件不存在: {test_file}")
            results[test_name] = {"success": False, "error": "File not found"}
            continue
        
        try:
            # 使用exec运行测试文件
            with open(test_path, 'r', encoding='utf-8') as f:
                test_code = f.read()
            
            # 创建一个新的命名空间来执行测试
            test_namespace = {}
            exec(test_code, test_namespace)
            
            # 查找并运行main函数
            if 'main' in test_namespace and asyncio.iscoroutinefunction(test_namespace['main']):
                await test_namespace['main']()
                results[test_name] = {"success": True}
            else:
                logger.warning(f"⚠️  测试文件中未找到async main函数")
                results[test_name] = {"success": False, "error": "No async main function"}
                
        except Exception as e:
            logger.error(f"❌ 测试运行失败: {e}")
            results[test_name] = {"success": False, "error": str(e)}
    
    # 打印最终报告
    total_time = time.time() - total_start
    
    logger.info("\n" + "=" * 80)
    logger.info("所有测试完成 - 最终报告")
    logger.info("=" * 80)
    logger.info(f"总耗时: {total_time:.2f}秒")
    logger.info(f"测试数量: {len(all_tests)}")
    
    success_count = sum(1 for r in results.values() if r.get("success"))
    logger.info(f"成功: {success_count}/{len(all_tests)}")
    logger.info(f"失败: {len(all_tests) - success_count}/{len(all_tests)}")
    
    for test_name, result in results.items():
        status = "✅" if result.get("success") else "❌"
        logger.info(f"\n{status} {test_name}")
        if not result.get("success") and "error" in result:
            logger.info(f"   错误: {result.get('error')}")
    
    logger.info("\n" + "=" * 80)
    if success_count == len(all_tests):
        logger.info("🎉 所有测试成功完成！")
    else:
        logger.warning(f"⚠️  有 {len(all_tests) - success_count} 个测试失败")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
