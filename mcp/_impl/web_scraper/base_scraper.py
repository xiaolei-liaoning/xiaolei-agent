"""
BaseScraper - Playwright浏览器池管理基类

工业级设计：
- 全局单例浏览器池，按站点名复用浏览器实例
- stealth反检测注入（navigator.webdriver、随机UA）
- 同站点串行锁（asyncio.Lock）
- 闲置超时自动清理
"""
import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# 随机UA池（主流桌面浏览器）
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# stealth注入脚本：覆盖webdriver检测
_STEALTH_JS = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en'],
    });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'permissions', {
        get: () => ({
            query: () => Promise.resolve({ state: 'granted' }),
        }),
    });
}
"""


class BaseScraper:
    """Playwright浏览器池管理基类（全局单例）"""

    _instance = None
    _browser_pool: Dict[str, Tuple] = {}  # {site_name: (browser, context, page, last_used)}
    _locks: Dict[str, asyncio.Lock] = {}
    _global_lock: Optional[asyncio.Lock] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, site_name: str = "default"):
        if self._initialized:
            return
        self._initialized = True
        self._browser_pool = {}
        self._locks = {}
        self._global_lock = None
        self.site_name = site_name
        
        # IP代理配置（暂时禁用，因为连接失败）
        self.proxies = None
        
        # 测试代理可用性
        # self._test_proxy()

    @staticmethod
    def _get_random_ua() -> str:
        return random.choice(_USER_AGENTS)
    
    def _test_proxy(self):
        """测试代理可用性"""
        try:
            import requests
            
            # 测试代理连接
            response = requests.get(
                "https://www.baidu.com",
                proxies=self.proxies,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"代理连接成功: {self.proxies['http']}")
                return True
            else:
                logger.warning(f"代理连接失败，状态码: {response.status_code}")
                return False
                
        except Exception as e:
            logger.warning(f"代理测试失败: {e}")
            return False
    
    async def download_file(self, url: str, save_path: str, timeout: int = 60):
        """下载文件
        
        Args:
            url: 文件URL
            save_path: 保存路径
            timeout: 超时时间（秒）
            
        Returns:
            bool: 下载是否成功
        """
        try:
            import requests
            import os
            
            # 确保目录存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # 使用代理下载
            response = requests.get(
                url,
                proxies=self.proxies,
                timeout=timeout,
                stream=True
            )
            
            response.raise_for_status()
            
            # 保存文件
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"文件下载成功: {url} -> {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"文件下载失败: {url} - {e}")
            return False
    
    async def download_images(self, page, selector: str, save_dir: str, max_images: int = 10):
        """下载页面中的图片
        
        Args:
            page: Playwright页面对象
            selector: 图片选择器
            save_dir: 保存目录
            max_images: 最大下载数量
            
        Returns:
            List[str]: 下载的图片路径列表
        """
        try:
            import os
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 获取图片元素
            image_elements = await page.query_selector_all(selector)
            
            downloaded_paths = []
            for i, element in enumerate(image_elements[:max_images]):
                # 获取图片URL
                img_url = await element.get_attribute('src')
                if not img_url:
                    continue
                
                # 确保URL完整
                if not img_url.startswith(('http://', 'https://')):
                    # 相对路径，需要拼接
                    img_url = await page.evaluate('(elem) => new URL(elem.src, document.baseURI).href', element)
                
                # 生成保存路径
                img_name = f"image_{i+1}_{img_url.split('/')[-1].split('?')[0]}"
                save_path = os.path.join(save_dir, img_name)
                
                # 下载图片
                if await self.download_file(img_url, save_path):
                    downloaded_paths.append(save_path)
            
            logger.info(f"图片下载完成: {len(downloaded_paths)}/{len(image_elements[:max_images])}")
            return downloaded_paths
            
        except Exception as e:
            logger.error(f"图片下载失败: {e}")
            return []
    
    async def download_videos(self, page, selector: str, save_dir: str, max_videos: int = 5):
        """下载页面中的视频
        
        Args:
            page: Playwright页面对象
            selector: 视频选择器
            save_dir: 保存目录
            max_videos: 最大下载数量
            
        Returns:
            List[str]: 下载的视频路径列表
        """
        try:
            import os
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 获取视频元素
            video_elements = await page.query_selector_all(selector)
            
            downloaded_paths = []
            for i, element in enumerate(video_elements[:max_videos]):
                # 获取视频URL
                video_url = await element.get_attribute('src')
                if not video_url:
                    # 尝试获取source标签
                    source = await element.query_selector('source')
                    if source:
                        video_url = await source.get_attribute('src')
                
                if not video_url:
                    continue
                
                # 确保URL完整
                if not video_url.startswith(('http://', 'https://')):
                    video_url = await page.evaluate('(elem) => new URL(elem.src, document.baseURI).href', element)
                
                # 生成保存路径
                video_name = f"video_{i+1}_{video_url.split('/')[-1].split('?')[0]}"
                save_path = os.path.join(save_dir, video_name)
                
                # 下载视频
                if await self.download_file(video_url, save_path, timeout=120):
                    downloaded_paths.append(save_path)
            
            logger.info(f"视频下载完成: {len(downloaded_paths)}/{len(video_elements[:max_videos])}")
            return downloaded_paths
            
        except Exception as e:
            logger.error(f"视频下载失败: {e}")
            return []
    
    async def download_audio(self, page, selector: str, save_dir: str, max_audio: int = 5):
        """下载页面中的音频
        
        Args:
            page: Playwright页面对象
            selector: 音频选择器
            save_dir: 保存目录
            max_audio: 最大下载数量
            
        Returns:
            List[str]: 下载的音频路径列表
        """
        try:
            import os
            
            # 确保目录存在
            os.makedirs(save_dir, exist_ok=True)
            
            # 获取音频元素
            audio_elements = await page.query_selector_all(selector)
            
            downloaded_paths = []
            for i, element in enumerate(audio_elements[:max_audio]):
                # 获取音频URL
                audio_url = await element.get_attribute('src')
                if not audio_url:
                    continue
                
                # 确保URL完整
                if not audio_url.startswith(('http://', 'https://')):
                    audio_url = await page.evaluate('(elem) => new URL(elem.src, document.baseURI).href', element)
                
                # 生成保存路径
                audio_name = f"audio_{i+1}_{audio_url.split('/')[-1].split('?')[0]}"
                save_path = os.path.join(save_dir, audio_name)
                
                # 下载音频
                if await self.download_file(audio_url, save_path, timeout=60):
                    downloaded_paths.append(save_path)
            
            logger.info(f"音频下载完成: {len(downloaded_paths)}/{len(audio_elements[:max_audio])}")
            return downloaded_paths
            
        except Exception as e:
            logger.error(f"音频下载失败: {e}")
            return []
    
    async def extract_tables(self, page, selector: str = 'table'):
        """提取页面中的表格数据
        
        Args:
            page: Playwright页面对象
            selector: 表格选择器
            
        Returns:
            List[List[List[str]]]: 表格数据列表
        """
        try:
            # 提取表格数据
            tables = await page.evaluate('''
                (selector) => {
                    const tables = document.querySelectorAll(selector);
                    const results = [];
                    
                    tables.forEach(table => {
                        const rows = table.querySelectorAll('tr');
                        const tableData = [];
                        
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('th, td');
                            const rowData = [];
                            
                            cells.forEach(cell => {
                                rowData.push(cell.textContent.trim());
                            });
                            
                            if (rowData.length > 0) {
                                tableData.push(rowData);
                            }
                        });
                        
                        if (tableData.length > 0) {
                            results.push(tableData);
                        }
                    });
                    
                    return results;
                }
            ''', selector)
            
            logger.info(f"表格提取完成: {len(tables)} 个表格")
            return tables
            
        except Exception as e:
            logger.error(f"表格提取失败: {e}")
            return []

    @staticmethod
    def _get_global_lock() -> asyncio.Lock:
        """获取/创建全局异步锁"""
        if BaseScraper._global_lock is None:
            BaseScraper._global_lock = asyncio.Lock()
        return BaseScraper._global_lock

    @staticmethod
    def _get_site_lock(site_name: str) -> asyncio.Lock:
        """获取/创建站点级锁，确保同站点串行"""
        if site_name not in BaseScraper._locks:
            BaseScraper._locks[site_name] = asyncio.Lock()
        return BaseScraper._locks[site_name]

    async def get_browser(self, site_name: str, timeout: float = 30.0):
        """
        获取/创建浏览器实例（热启动复用）

        Args:
            site_name: 站点标识（如 weibo、baidu）
            timeout: 启动超时（秒）

        Returns:
            (browser, context, page) 元组
        """
        global_lock = self._get_global_lock()
        site_lock = self._get_site_lock(site_name)

        async with global_lock:
            # 检查已有实例是否可用
            if site_name in self._browser_pool:
                browser, context, page, last_used = self._browser_pool[site_name]
                try:
                    # 检查浏览器连接是否仍然有效
                    if browser.is_connected():
                        self._browser_pool[site_name] = (browser, context, page, time.time())
                        logger.debug(f"复用浏览器实例: {site_name}")
                        return browser, context, page
                    else:
                        # 已断开，清理
                        logger.warning(f"浏览器实例已断开，重建: {site_name}")
                        del self._browser_pool[site_name]
                except Exception:
                    del self._browser_pool[site_name]

            # 创建新实例
            logger.info(f"创建浏览器实例: {site_name}")

            from playwright.async_api import async_playwright

            ua = self._get_random_ua()
            pw = await async_playwright().start()

            # 检查代理是否可用
            proxy_config = None
            if self.proxies and self._test_proxy():
                proxy_config = {
                    "server": self.proxies["http"],
                }
                logger.info("使用代理: %s", self.proxies["http"])
            else:
                logger.info("未使用代理")
            
            browser = await pw.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    # 启用图片和CSS以获得更好的用户体验
                ],
                proxy=proxy_config,
                timeout=timeout * 1000,
            )

            context = await browser.new_context(
                user_agent=ua,
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )

            # 注入stealth脚本
            await context.add_init_script(_STEALTH_JS)

            page = await context.new_page()
            # 设置默认超时
            page.set_default_timeout(timeout * 1000)
            page.set_default_navigation_timeout(timeout * 1000)

            self._browser_pool[site_name] = (browser, context, page, time.time())
            logger.info(f"浏览器实例创建完成: {site_name} (UA: {ua[:50]}...)")
            return browser, context, page

    async def close_browser(self, site_name: str):
        """关闭指定站点的浏览器"""
        if site_name not in self._browser_pool:
            return

        browser, context, page, _ = self._browser_pool.pop(site_name, (None, None, None, 0))
        try:
            if page:
                await page.close()
            if context:
                await context.close()
            if browser:
                await browser.close()
            logger.info(f"浏览器已关闭: {site_name}")
        except Exception as e:
            logger.warning(f"关闭浏览器异常 [{site_name}]: {e}")

    async def close_all(self):
        """关闭所有浏览器实例"""
        sites = list(self._browser_pool.keys())
        for site in sites:
            await self.close_browser(site)
        logger.info("所有浏览器实例已关闭")

    async def cleanup_idle(self, timeout: int = 600):
        """
        清理闲置超时的浏览器

        Args:
            timeout: 闲置超时秒数（默认600s=10分钟）
        """
        now = time.time()
        idle_sites = [
            name for name, (_, _, _, last_used) in self._browser_pool.items()
            if (now - last_used) > timeout
        ]
        for site in idle_sites:
            logger.info(f"清理闲置浏览器: {site} (闲置 {int(now - self._browser_pool[site][3])}s)")
            await self.close_browser(site)

    @staticmethod
    async def take_screenshot(page, path: str):
        """
        截图保存

        Args:
            page: Playwright page对象
            path: 保存路径
        """
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path_obj), full_page=True)
        logger.info(f"截图已保存: {path}")

    # 子类需实现的方法
    def get_hot_list(self, top_n: int = 10) -> List[dict]:
        raise NotImplementedError

    def search(self, keyword: str, top_n: int = 10) -> List[dict]:
        raise NotImplementedError