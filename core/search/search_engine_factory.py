"""百度搜索实现 - 替代 DuckDuckGo"""

import logging
from typing import List, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseSearchEngine(ABC):
    """搜索引擎基类"""

    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """执行搜索"""
        pass


class DuckDuckGoSearch(BaseSearchEngine):
    """DuckDuckGo 搜索引擎（国外用户使用）"""

    def __init__(self):
        self._ddgs = None
        self._init_engine()

    def _init_engine(self):
        """初始化引擎"""
        try:
            from duckduckgo_search import DDGS
            self._ddgs = DDGS()
            logger.info("DuckDuckGo 搜索引擎初始化成功")
        except Exception as e:
            logger.warning(f"DuckDuckGo 搜索引擎初始化失败: {e}")

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """执行 DuckDuckGo 搜索"""
        if not self._ddgs:
            logger.warning("DuckDuckGo 引擎未初始化")
            return []

        results = []
        try:
            items = self._ddgs.text(query, max_results=num_results)
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                    "source": "duckduckgo"
                })
        except Exception as e:
            logger.error(f"DuckDuckGo 搜索失败: {e}")

        return results


class BaiduSearch(BaseSearchEngine):
    """百度搜索（国内用户使用）"""

    def __init__(self):
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """执行百度搜索"""
        try:
            import requests
            from bs4 import BeautifulSoup

            url = f"https://www.baidu.com/s?wd={requests.utils.quote(query)}"
            response = requests.get(url, headers=self._headers, timeout=10)
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            for h3 in soup.find_all('h3')[:num_results]:
                link = h3.find('a')
                if link:
                    title = h3.get_text(strip=True)
                    url = link.get('href', '')
                    
                    if url.startswith('/link?url='):
                        url = 'https://www.baidu.com' + url
                    
                    next_p = h3.find_next('p')
                    snippet = next_p.get_text(strip=True)[:500] if next_p else ''
                    
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "source": "baidu"
                    })

            logger.info(f"百度搜索成功: {len(results)} 个结果")
            return results

        except ImportError:
            logger.error("请安装 requests 和 beautifulsoup4: pip install requests beautifulsoup4")
            return []
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            return []


class BingSearch(BaseSearchEngine):
    """Bing 搜索"""

    def __init__(self):
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """执行 Bing 搜索"""
        try:
            import requests
            from bs4 import BeautifulSoup

            url = f"https://www.bing.com/search?q={requests.utils.quote(query)}"
            response = requests.get(url, headers=self._headers, timeout=10)
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            for item in soup.select('.b_algo')[:num_results]:
                title_elem = item.select_one('h2 a')
                snippet_elem = item.select_one('.b_paractl')
                if title_elem:
                    results.append({
                        "title": title_elem.get_text(),
                        "url": title_elem.get('href', ''),
                        "snippet": snippet_elem.get_text() if snippet_elem else '',
                        "source": "bing"
                    })

            logger.info(f"Bing 搜索成功: {len(results)} 个结果")
            return results

        except ImportError:
            logger.error("请安装 requests 和 beautifulsoup4: pip install requests beautifulsoup4")
            return []
        except Exception as e:
            logger.error(f"Bing 搜索失败: {e}")
            return []


class FallbackSearch(BaseSearchEngine):
    """回退搜索 - 使用预定义数据（当所有引擎都不可用时）"""

    def __init__(self):
        self._mock_data = {
            "AI市场趋势": [
                {"title": "2024年AI市场发展趋势分析", "url": "https://example.com/ai-trends-2024", "snippet": "2024年AI市场将继续保持高速增长，预计市场规模将达到5000亿美元。", "source": "mock"},
                {"title": "人工智能在各行业的应用现状", "url": "https://example.com/ai-applications", "snippet": "AI技术已广泛应用于医疗、金融、制造等领域，显著提升了效率。", "source": "mock"},
                {"title": "生成式AI的市场前景预测", "url": "https://example.com/genai-market", "snippet": "生成式AI将成为2024年最热门的AI技术方向，市场潜力巨大。", "source": "mock"},
            ],
            "default": [
                {"title": "搜索结果示例", "url": "https://example.com", "snippet": "这是搜索结果的示例内容，当无法访问搜索引擎时使用模拟数据。", "source": "mock"},
            ]
        }

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """返回模拟数据"""
        for key, results in self._mock_data.items():
            if key in query:
                logger.info(f"使用模拟数据（关键词匹配: {key}）")
                return results[:num_results]

        logger.info("使用默认模拟数据")
        return self._mock_data["default"][:num_results]


class SearchEngineFactory:
    """搜索引擎工厂"""

    _engines = {
        "duckduckgo": DuckDuckGoSearch,
        "baidu": BaiduSearch,
        "bing": BingSearch,
        "fallback": FallbackSearch,
    }

    @classmethod
    def create(cls, engine_type: str = "auto") -> BaseSearchEngine:
        """
        创建搜索引擎

        Args:
            engine_type: 引擎类型
                - "auto": 自动选择（优先国内可访问的引擎）
                - "duckduckgo": DuckDuckGo（国外）
                - "baidu": 百度（国内）
                - "bing": Bing
                - "fallback": 回退（模拟数据）

        Returns:
            搜索引擎实例
        """
        if engine_type == "auto":
            return cls.create("baidu")

        engine_class = cls._engines.get(engine_type, FallbackSearch)
        return engine_class()

    @classmethod
    def create_with_fallback(cls) -> BaseSearchEngine:
        """创建带回退机制的搜索引擎（快速模式，不做连通性测试）"""
        for engine_type in ["baidu", "bing", "duckduckgo"]:
            try:
                engine = cls.create(engine_type)
                if engine_type != "fallback":
                    # 跳过连通性测试——失败由调用方处理
                    logger.info(f"搜索引擎 {engine_type} 已实例化")
                    return engine
            except Exception as e:
                logger.warning(f"搜索引擎 {engine_type} 不可用: {e}")

        logger.warning("所有搜索引擎都不可用，使用模拟数据")
        return cls.create("fallback")


def get_search_engine(engine_type: str = "auto") -> BaseSearchEngine:
    """获取搜索引擎实例（便捷函数）"""
    return SearchEngineFactory.create_with_fallback()