#!/usr/bin/env python3
"""
技能市场生态系统 - 完整演示

展示如何使用技能市场的所有功能。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from skills.marketplace.registry import SkillRegistry, SkillMetadata
from skills.marketplace.version_manager import VersionManager
from skills.marketplace.dependency_resolver import DependencyResolver
from skills.marketplace.rating_system import RatingSystem
from skills.marketplace.search_engine import SkillSearchEngine
from skills.marketplace.validator import SkillValidator
from skills.marketplace.publisher import SkillPublisher


def demo_workflow():
    """演示完整的技能市场工作流程"""
    
    print("\n" + "="*80)
    print("🚀 技能市场生态系统 - 完整演示")
    print("="*80 + "\n")
    
    # ========== 1. 初始化系统组件 ==========
    print("📦 步骤 1: 初始化系统组件")
    print("-" * 80)
    
    registry = SkillRegistry()
    version_manager = VersionManager()
    dependency_resolver = DependencyResolver(version_manager)
    rating_system = RatingSystem()
    search_engine = SkillSearchEngine(registry)
    validator = SkillValidator()
    publisher = SkillPublisher(registry, version_manager, validator)
    
    print("✅ 所有组件初始化完成\n")
    
    # ========== 2. 创建和注册技能 ==========
    print("📝 步骤 2: 创建和注册技能")
    print("-" * 80)
    
    # 模拟创建多个技能
    skills_to_register = [
        SkillMetadata(
            name="weather_query",
            version="1.0.0",
            description="查询实时天气信息",
            author="developer_1",
            email="dev1@example.com",
            category="utility",
            tags=["weather", "forecast", "temperature"],
            keywords=["天气", "温度", "预报", "气象"]
        ),
        SkillMetadata(
            name="data_analyzer",
            version="1.0.0",
            description="数据分析工具",
            author="developer_2",
            email="dev2@example.com",
            category="analysis",
            tags=["data", "analysis", "statistics"],
            keywords=["数据", "分析", "统计", "图表"]
        ),
        SkillMetadata(
            name="text_translator",
            version="1.0.0",
            description="多语言文本翻译",
            author="developer_3",
            email="dev3@example.com",
            category="utility",
            tags=["translation", "language", "text"],
            keywords=["翻译", "语言", "文本", "多语言"]
        ),
        SkillMetadata(
            name="image_processor",
            version="1.0.0",
            description="图像处理工具",
            author="developer_4",
            email="dev4@example.com",
            category="media",
            tags=["image", "processing", "filter"],
            keywords=["图像", "处理", "滤镜", "编辑"]
        ),
    ]
    
    for skill in skills_to_register:
        success = registry.register_skill(skill)
        version_manager.add_version(skill.name, skill.version)
        status = "✅" if success else "❌"
        print(f"{status} 注册技能: {skill.name}@{skill.version}")
    
    print(f"\n✅ 成功注册 {len(skills_to_register)} 个技能\n")
    
    # ========== 3. 设置依赖关系 ==========
    print("🔗 步骤 3: 设置技能依赖关系")
    print("-" * 80)
    
    dependency_resolver.register_dependencies("weather_app", {
        "weather_query": "^1.0.0",
        "data_analyzer": "~1.0.0"
    })
    
    dependency_resolver.register_dependencies("translation_tool", {
        "text_translator": "^1.0.0"
    })
    
    print("✅ 依赖关系设置完成")
    
    # 解析依赖树
    success, order, errors = dependency_resolver.resolve_dependencies("weather_app")
    if success:
        print(f"✅ weather_app 依赖解析成功，安装顺序: {order}")
    
    # 显示依赖树
    tree = dependency_resolver.get_dependency_tree("weather_app")
    print(f"📊 依赖树结构:")
    print(f"   {tree['name']} (v{tree['version']})")
    for child in tree['children']:
        print(f"   └── {child['name']} (constraint: {child.get('constraint', 'N/A')})")
    
    print()
    
    # ========== 4. 添加用户评分 ==========
    print("⭐ 步骤 4: 添加用户评分和评论")
    print("-" * 80)
    
    # 为 weather_query 添加评分
    ratings_data = [
        ("user_001", "weather_query", "1.0.0", 5, "非常准确的天气预报！"),
        ("user_002", "weather_query", "1.0.0", 4, "很好用，希望能支持更多城市"),
        ("user_003", "weather_query", "1.0.0", 5, "完美！"),
        ("user_004", "data_analyzer", "1.0.0", 4, "功能强大"),
        ("user_005", "data_analyzer", "1.0.0", 5, "数据分析很专业"),
        ("user_006", "text_translator", "1.0.0", 3, "基本够用"),
        ("user_007", "image_processor", "1.0.0", 5, "图像处理效果很棒！"),
    ]
    
    for user_id, skill_name, version, rating, comment in ratings_data:
        rating_system.add_rating(user_id, skill_name, version, rating, comment)
        print(f"✅ {user_id} 给 {skill_name} 评分: {'⭐' * rating}")
    
    print()
    
    # 获取评分汇总
    weather_summary = rating_system.get_skill_summary("weather_query")
    print(f"📊 weather_query 评分汇总:")
    print(f"   平均评分: {weather_summary.average_rating:.2f}/5.0")
    print(f"   评分人数: {weather_summary.total_ratings}")
    print(f"   评分分布: {weather_summary.rating_distribution}")
    print()
    
    # ========== 5. 搜索和发现技能 ==========
    print("🔍 步骤 5: 搜索和发现技能")
    print("-" * 80)
    
    # 关键词搜索
    print("🔎 搜索关键词 '天气':")
    results = search_engine.search(query="天气", limit=5)
    for i, result in enumerate(results, 1):
        skill = result['skill']
        score = result['relevance_score']
        print(f"   {i}. {skill['name']} (相关性: {score:.2f}, 评分: {skill['rating']:.1f})")
    
    print()
    
    # 标签搜索
    print("🏷️  按标签搜索 ['data', 'analysis']:")
    results = search_engine.search_by_tags(["data", "analysis"], limit=5)
    for i, result in enumerate(results, 1):
        skill = result['skill']
        print(f"   {i}. {skill['name']} (匹配度: {result['relevance_score']:.2f})")
    
    print()
    
    # 分类浏览
    print("📂 浏览 'utility' 分类:")
    results = search_engine.search_by_category("utility", limit=5)
    for i, result in enumerate(results, 1):
        skill = result['skill']
        print(f"   {i}. {skill['name']} (评分: {skill['rating']:.1f}, 下载: {skill['downloads']})")
    
    print()
    
    # 个性化推荐
    print("💡 个性化推荐（基于使用历史）:")
    recommendations = search_engine.get_recommendations(
        user_history=["weather_query"],
        limit=3
    )
    for i, rec in enumerate(recommendations, 1):
        skill = rec['skill']
        print(f"   {i}. {skill['name']} - {skill['description'][:50]}")
    
    if not recommendations:
        print("   (暂无推荐，需要更多用户行为数据)")
    
    print()
    
    # 相似技能
    print("🔀 查找与 'weather_query' 相似的技能:")
    similar = search_engine.get_similar_skills("weather_query", limit=3)
    for i, sim in enumerate(similar, 1):
        skill = sim['skill']
        print(f"   {i}. {skill['name']} (相似度: {sim['similarity']:.2f})")
    
    if not similar:
        print("   (暂无相似技能)")
    
    print()
    
    # ========== 6. 获取排行榜 ==========
    print("🏆 步骤 6: 技能排行榜")
    print("-" * 80)
    
    # Top评分技能
    print("⭐ Top评分技能:")
    top_rated = rating_system.get_top_rated_skills(min_ratings=1, limit=5)
    for i, skill_info in enumerate(top_rated, 1):
        print(f"   {i}. {skill_info['skill_name']} (评分: {skill_info['average_rating']:.2f}, "
              f"评分数: {skill_info['total_ratings']})")
    
    print()
    
    # 热门技能
    print("🔥 最近7天热门技能:")
    trending = rating_system.get_trending_skills(days=7, limit=5)
    for i, skill_info in enumerate(trending, 1):
        print(f"   {i}. {skill_info['skill_name']} (近期评分: {skill_info['recent_ratings']})")
    
    if not trending:
        print("   (暂无近期评分数据)")
    
    print()
    
    # ========== 7. 系统统计 ==========
    print("📊 步骤 7: 系统统计信息")
    print("-" * 80)
    
    registry_stats = registry.get_statistics()
    print(f"📦 技能注册表:")
    print(f"   总技能数: {registry_stats['total_skills']}")
    print(f"   已验证技能: {registry_stats['verified_skills']}")
    print(f"   分类分布: {registry_stats['categories']}")
    print(f"   总下载量: {registry_stats['total_downloads']}")
    print(f"   平均评分: {registry_stats['average_rating']:.2f}")
    print()
    
    rating_stats = rating_system.get_statistics()
    print(f"⭐ 评分系统:")
    print(f"   总评分数: {rating_stats['total_ratings']}")
    print(f"   被评分技能: {rating_stats['total_skills_rated']}")
    print(f"   活跃用户: {rating_stats['total_users']}")
    print(f"   全局平均分: {rating_stats['global_average_rating']:.2f}")
    print()
    
    search_stats = search_engine.get_statistics()
    print(f"🔍 搜索引擎:")
    print(f"   索引技能数: {search_stats['total_indexed_skills']}")
    print(f"   关键词索引: {search_stats['keyword_index_size']}")
    print(f"   标签索引: {search_stats['tag_index_size']}")
    print(f"   分类数: {len(search_stats['categories'])}")
    print()
    
    dep_stats = dependency_resolver.get_statistics()
    print(f"🔗 依赖管理:")
    print(f"   有依赖的技能: {dep_stats['skills_with_dependencies']}")
    print(f"   总依赖关系: {dep_stats['total_dependencies']}")
    print(f"   平均每技能依赖: {dep_stats['average_dependencies_per_skill']:.2f}")
    print()
    
    # ========== 8. 验证示例技能 ==========
    print("✅ 步骤 8: 验证示例技能")
    print("-" * 80)
    
    example_path = Path(__file__).parent / "example_skill"
    if example_path.exists():
        validation_result = validator.validate_skill(example_path)
        
        print(f"技能: {example_path.name}")
        print(f"验证状态: {'✅ 通过' if validation_result.is_valid else '❌ 失败'}")
        
        if validation_result.warnings:
            print(f"警告 ({len(validation_result.warnings)}):")
            for warning in validation_result.warnings[:3]:
                print(f"   ⚠️  {warning}")
        
        if validation_result.suggestions:
            print(f"建议 ({len(validation_result.suggestions)}):")
            for suggestion in validation_result.suggestions[:3]:
                print(f"   💡 {suggestion}")
    else:
        print("⚠️  示例技能不存在")
    
    print()
    
    # ========== 总结 ==========
    print("="*80)
    print("🎉 演示完成！")
    print("="*80)
    print()
    print("✨ 技能市场生态系统核心功能:")
    print("   ✅ 技能注册和管理")
    print("   ✅ 语义化版本控制")
    print("   ✅ 依赖关系解析")
    print("   ✅ 用户评分系统")
    print("   ✅ 智能搜索和推荐")
    print("   ✅ 代码质量验证")
    print("   ✅ 技能打包发布")
    print()
    print("📚 下一步:")
    print("   1. 使用 CLI 工具创建你的第一个技能")
    print("   2. 启动 Web API 服务")
    print("   3. 浏览技能市场文档")
    print()


if __name__ == '__main__':
    try:
        demo_workflow()
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
