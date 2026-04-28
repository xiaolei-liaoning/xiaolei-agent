
"""
ScraperDispatcher - 爬虫统一分发器

功能:
    - 统一入口 execute(site_name, action, **kwargs)
    - 自动注册所有爬虫模块
    - auto_analyze=True 时自动保存 CSV 到 skills/output/ 目录
    - CSV格式: 排名,标题,热度,链接（UTF-8-BOM编码）
    - 所有爬虫加载失败时返回友好错误信息而非崩溃
"""
import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / 'output'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 站点名称 → (模块路径, 类名) 映射
_SCRAPER_REGISTRY: Dict[str, Dict[str, str]] = {
    '微博': {
        'module': 'skills.web_scraper.weibo_scraper',
        'class': 'WeiboScraper',
    },
    '百度': {
        'module': 'skills.web_scraper.baidu_scraper',
        'class': 'BaiduScraper',
    },
    'B站': {
        'module': 'skills.web_scraper.bilibili_scraper',
        'class': 'BilibiliScraper',
    },
    'bilibili': {
        'module': 'skills.web_scraper.bilibili_scraper',
        'class': 'BilibiliScraper',
    },
    '抖音': {
        'module': 'skills.web_scraper.douyin_scraper',
        'class': 'DouyinScraper',
    },
    'GitHub': {
        'module': 'skills.web_scraper.github_scraper',
        'class': 'GitHubTrendingScraper',
    },
    '搜索引擎': {
        'module': 'skills.web_scraper.search_scraper',
        'class': 'SearchEngineScraper',
    },
    '知乎': {
        'module': 'skills.web_scraper.zhihu_scraper',
        'class': 'ZhihuScraper',
    },
    '今日头条': {
        'module': 'skills.web_scraper.toutiao_scraper',
        'class': 'ToutiaoScraper',
    },
}

# 站点别名映射（用户可能用不同名称指代同一站点）
_SITE_ALIASES: Dict[str, str] = {
    '微博': '微博',
    'weibo': '微博',
    '微薄': '微博',
    '百度': '百度',
    'baidu': '百度',
    'B站': 'B站',
    'bilibili': 'B站',
    '哔哩哔哩': 'B站',
    'Bilibili': 'B站',
    '抖音': '抖音',
    'douyin': '抖音',
    'tiktok': '抖音',
    'GitHub': 'GitHub',
    'github': 'GitHub',
    'github trending': 'GitHub',
    '搜索': '搜索引擎',
    'search': '搜索引擎',
    '知乎': '知乎',
    'zhihu': '知乎',
    '今日头条': '今日头条',
    '头条': '今日头条',
    'toutiao': '今日头条',
}


class ScraperDispatcher:
    """
    爬虫统一分发器

    负责管理所有爬虫实例的生命周期，提供统一的调用接口。
    自动处理CSV保存和格式化输出。

    Usage:
        dispatcher = ScraperDispatcher()
        result = dispatcher.execute(site_name='微博', action='热搜top10')
    """

    def __init__(self) -> None:
        self._scrapers: Dict[str, Any] = {}
        self._last_scrape_result: Optional[Dict] = None
        self._init_scrapers()

    def _init_scrapers(self) -> None:
        """
        自动注册所有爬虫实例

        单个爬虫加载失败不影响其他爬虫，仅记录warning日志。
        """
        loaded: List[str] = []
        failed: List[str] = []

        for site_name, config in _SCRAPER_REGISTRY.items():
            # 跳过重复注册（别名站点共用实例）
            canonical_name = _SITE_ALIASES.get(site_name, site_name)
            if canonical_name in self._scrapers and site_name != canonical_name:
                self._scrapers[site_name] = self._scrapers[canonical_name]
                loaded.append(site_name)
                continue

            try:
                module_path = config['module']
                class_name = config['class']

                # 动态导入模块
                import importlib
                module = importlib.import_module(module_path)
                scraper_class = getattr(module, class_name)

                # 实例化
                instance = scraper_class()
                self._scrapers[site_name] = instance
                loaded.append(site_name)

            except ImportError as e:
                logger.warning(f"[{site_name}] 模块导入失败: {e}")
                failed.append(site_name)
            except AttributeError as e:
                logger.warning(f"[{site_name}] 类不存在: {e}")
                failed.append(site_name)
            except Exception as e:
                logger.warning(f"[{site_name}] 爬虫初始化失败: {e}")
                failed.append(site_name)

        # 补全别名引用
        for alias, canonical in _SITE_ALIASES.items():
            if alias not in self._scrapers and canonical in self._scrapers:
                self._scrapers[alias] = self._scrapers[canonical]

        logger.info(f"爬虫注册完成 - 成功: {loaded}, 失败: {failed}")

    @property
    def available_sites(self) -> List[str]:
        """获取可用站点列表"""
        canonical_sites = ['微博', '百度', 'B站', '抖音', 'GitHub', '搜索引擎', '知乎', '今日头条']
        return [s for s in canonical_sites if s in self._scrapers]

    def execute(
        self,
        site_name: str = '微博',
        action: str = '热搜top10',
        auto_analyze: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        统一爬虫执行入口

        Args:
            site_name: 站点名称（微博/百度/B站/抖音）
            action: 操作类型（热搜top10/热榜/搜索/热门）
            auto_analyze: 是否自动保存CSV
            **kwargs: 额外参数（keyword, top_n等）

        Returns:
            {
                "success": bool,
                "site": str,
                "action": str,
                "count": int,
                "data": List[Dict],
                "reply": str,          # 格式化回复文本
                "csv_path": str|None,  # CSV保存路径
            }
        """
        # 规范化站点名称
        normalized = _SITE_ALIASES.get(site_name, site_name)

        if normalized not in self._scrapers:
            available = self.available_sites
            return {
                'success': False,
                'site': site_name,
                'action': action,
                'count': 0,
                'data': [],
                'reply': f'不支持的站点「{site_name}」，当前支持: {", ".join(available) if available else "无可用站点"}',
                'csv_path': None,
                'error': f'不支持的站点: {site_name}',
            }

        scraper = self._scrapers[normalized]
        top_n = kwargs.get('top_n', 10)

        try:
            # 重置上次结果
            self._last_scrape_result = None
            
            # 路由action到对应方法
            results = self._route_action(scraper, action, **kwargs)

            if results and auto_analyze:
                csv_path = self._save_to_csv(normalized, results)
            else:
                csv_path = None

            return {
                'success': True,
                'site': normalized,
                'action': action,
                'count': len(results) if results else 0,
                'data': results or [],
                'reply': self._format_reply(normalized, results, action),
                'csv_path': str(csv_path) if csv_path else None,
                # 添加下载结果
                'images': self._last_scrape_result.get('images', []) if self._last_scrape_result is not None else [],
                'videos': self._last_scrape_result.get('videos', []) if self._last_scrape_result is not None else [],
                'audio': self._last_scrape_result.get('audio', []) if self._last_scrape_result is not None else [],
                'tables': self._last_scrape_result.get('tables', []) if self._last_scrape_result is not None else [],
            }

        except Exception as e:
            logger.error(f"爬虫执行异常 [{normalized}/{action}]: {e}", exc_info=True)
            return {
                'success': False,
                'site': normalized,
                'action': action,
                'count': 0,
                'data': [],
                'reply': f'爬取「{normalized}」{action}时出错: {e}',
                'csv_path': None,
                'error': str(e),
            }

    def _route_action(
        self,
        scraper: Any,
        action: str,
        **kwargs: Any,
    ) -> List[Dict[str, str]]:
        """
        路由action到爬虫实例的对应方法（兼容新旧接口）

        Args:
            scraper: 爬虫实例
            action: 操作类型
            **kwargs: 额外参数

        Returns:
            结果列表
        """
        import asyncio
        
        # 对于GitHub爬虫，优先使用get_hot_list方法（同步版本）
        if scraper.__class__.__name__ == 'GitHubTrendingScraper':
            return scraper.get_hot_list(top_n=kwargs.get('top_n', 10))
        
        # 检查是否有新的scrape方法
        if hasattr(scraper, 'scrape') and callable(getattr(scraper, 'scrape')):
            try:
                # 准备scrape方法的参数
                scrape_kwargs = {
                    'action': action,
                    'top_n': kwargs.get('top_n', 10),
                }
                
                # 如果有keyword参数，也传递过去
                if 'keyword' in kwargs:
                    scrape_kwargs['keyword'] = kwargs['keyword']
                
                # 规范化action参数，确保与爬虫期望的格式一致
                action_mapping = {
                    '热搜top10': '热搜',
                    '热榜': '热搜',
                    '热门': '热搜',
                    'hot': '热搜',
                    'search': '搜索',
                    '搜索': '搜索',
                }
                
                normalized_action = action_mapping.get(action, action)
                scrape_kwargs['action'] = normalized_action
                
                # 检查是否已经在事件循环中
                try:
                    loop = asyncio.get_running_loop()
                    # 如果有运行的事件循环，创建新线程运行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, scraper.scrape(**scrape_kwargs))
                        result = future.result(timeout=30)
                except RuntimeError:
                    # 没有运行的事件循环，直接运行
                    result = asyncio.run(scraper.scrape(**scrape_kwargs))
                
                if result.get('success'):
                    # 保存完整结果
                    self._last_scrape_result = result
                    return result.get('data', [])
                return []
            except Exception as e:
                logger.error("爬虫执行失败: %s", e)
                return []
        
        # 旧接口兼容
        top_n = kwargs.get('top_n', 10)

        if action in ('热搜top10', '热榜', '热门', 'hot'):
            return scraper.get_hot_list(top_n=top_n)
        elif action in ('搜索', 'search', '搜'):
            keyword = kwargs.get('keyword', '')
            if not keyword:
                logger.warning("搜索操作缺少keyword参数")
                return []
            return scraper.search(keyword, top_n=top_n)
        else:
            # 默认返回热搜
            logger.info(f"未知action「{action}」，默认返回热搜")
            return scraper.get_hot_list(top_n=top_n)

    def _save_to_csv(self, site_name: str, data: List[Dict[str, str]]) -> Optional[Path]:
        """
        保存数据为CSV文件

        编码: UTF-8-BOM（Excel友好）
        列: 排名, 标题, 热度, 链接

        Args:
            site_name: 站点名称
            data: 数据列表

        Returns:
            CSV文件路径，失败返回None
        """
        if not data:
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{site_name}_热搜_{timestamp}.csv'
        filepath = OUTPUT_DIR / filename

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['排名', '标题', '热度', '链接'],
                    extrasaction='ignore',
                )
                writer.writeheader()
                for i, item in enumerate(data, 1):
                    writer.writerow({
                        '排名': i,
                        '标题': item.get('title', '') or item.get('word', ''),
                        '热度': item.get('heat', '') or item.get('hot', '') or item.get('play', ''),
                        '链接': item.get('url', '') or item.get('link', ''),
                    })
            logger.info(f"CSV已保存: {filepath} ({len(data)}条)")
            return filepath
        except Exception as e:
            logger.error(f"CSV保存失败: {e}")
            return None

    def _format_reply(
        self,
        site_name: str,
        data: Optional[List[Dict[str, str]]],
        action: str = '热搜top10',
    ) -> str:
        """
        格式化回复文本

        Args:
            site_name: 站点名称
            data: 数据列表
            action: 操作类型

        Returns:
            格式化后的文本
        """
        if not data:
            return f'{site_name}暂无数据'

        action_label = '热搜' if '搜索' not in action else '搜索结果'
        display_n = min(len(data), 10)

        lines = [f'[{site_name} {action_label}] Top{display_n}:\n']
        for i, item in enumerate(data[:display_n], 1):
            title = item.get('title', '') or item.get('word', '未知')
            heat = item.get('heat', '') or item.get('hot', '') or item.get('play', '')
            heat_str = f' ({heat})' if heat else ''

            # 截断过长标题
            if len(title) > 50:
                title = title[:47] + '...'

            lines.append(f'{i}. {title}{heat_str}')

        return '\n'.join(lines)


# 全局单例
scraper_dispatcher = ScraperDispatcher()


# 便捷导出
__all__ = ['ScraperDispatcher', 'scraper_dispatcher']