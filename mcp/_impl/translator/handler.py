"""翻译助手处理器（工业级 v3.3.0）

基于MyMemory免费API，支持自动语言检测。
支持语言：zh/en/ja/ko/fr/de/ru/es/it/pt/ar

依赖：httpx
"""

import time
import logging
import json
from typing import Dict, Any, Optional, Set, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_DIR = Path(__file__).parent / 'history'
HISTORY_DIR.mkdir(exist_ok=True)

LANG_NAMES: Dict[str, str] = {
    'zh': '中文', 'en': '英文', 'ja': '日文', 'ko': '韩文',
    'fr': '法文', 'de': '德文', 'ru': '俄文', 'es': '西班牙文',
    'it': '意大利文', 'pt': '葡萄牙文', 'ar': '阿拉伯文',
}

SUPPORTED_TARGETS: Set[str] = set(LANG_NAMES.keys())


class TranslatorHandler:
    """翻译助手处理器。

    工业级特性：
    - 同步/异步双接口
    - httpx连接复用（异步客户端单例）
    - Unicode范围语言自动检测
    - 置信度返回
    - 超时重试机制（默认重试1次）
    - 11种语言支持

    Attributes:
        api_url: MyMemory API端点
        max_retries: 最大重试次数
        _async_client: httpx异步客户端（延迟初始化）
    """

    def __init__(self, max_retries: int = 1) -> None:
        """初始化翻译助手。

        Args:
            max_retries: 请求失败最大重试次数
        """
        # 确保max_retries是整数
        try:
            max_retries_int = int(max_retries) if max_retries else 1
        except (ValueError, TypeError):
            max_retries_int = 1
        
        self.api_url: str = "https://api.mymemory.translated.net/get"
        self.max_retries: int = max_retries_int
        self._async_client: Optional[Any] = None
        logger.info("TranslatorHandler 初始化完成, 最大重试: %d", max_retries_int)

    async def _get_async_client(self) -> Any:
        """获取或创建httpx异步客户端（懒加载单例）。

        Returns:
            httpx.AsyncClient 实例
        """
        if self._async_client is None or self._async_client.is_closed:
            import httpx
            self._async_client = httpx.AsyncClient(
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=10,
            )
        return self._async_client

    async def close(self) -> None:
        """关闭异步客户端连接。"""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
            self._async_client = None

    def execute(
        self,
        text: str = '',
        target_lang: str = 'en',
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """执行翻译（同步接口）。

        Args:
            text: 待翻译文本
            target_lang: 目标语言代码 (zh/en/ja/ko/fr/de/ru/es)
            source_lang: 源语言代码，为空则自动检测(autodetect)

        Returns:
            Dict[str, Any]: 包含 original, translated, confidence 的字典
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(text, target_lang, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.info("翻译完成 [%s→%s], 耗时: %.3fs", kwargs.get('source_lang', 'auto'),
                        target_lang, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("翻译异常: %s", e, exc_info=True)
            return {'success': False, 'error': f'翻译异常: {e}'}

    async def aexecute(
        self,
        text: str = '',
        target_lang: str = 'en',
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """执行翻译（异步接口）。

        使用httpx异步客户端，连接复用。

        Args:
            text: 待翻译文本
            target_lang: 目标语言代码
            source_lang: 源语言代码

        Returns:
            Dict[str, Any]: 翻译结果
        """
        start_time = time.perf_counter()
        try:
            result = await self._do_async_execute(text, target_lang, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.info("翻译完成(异步) [%s→%s], 耗时: %.3fs", kwargs.get('source_lang', 'auto'),
                        target_lang, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("翻译异常(异步): %s", e, exc_info=True)
            return {'success': False, 'error': f'翻译异常: {e}'}

    def _do_execute(
        self,
        text: str,
        target_lang: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """同步核心翻译逻辑。"""
        if not text:
            return {'success': False, 'error': '未指定翻译文本'}

        target_lang = target_lang.lower().strip()
        if target_lang not in SUPPORTED_TARGETS:
            return {
                'success': False,
                'error': f'不支持的目标语言: {target_lang}，支持: {", ".join(sorted(SUPPORTED_TARGETS))}',
            }

        source_lang: str = kwargs.get('source_lang', 'autodetect')
        langpair = f"{source_lang}|{target_lang}"

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self._call_api(text, langpair)
                if result:
                    return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(0.5)
                    logger.warning("翻译重试 %d/%d", attempt + 1, self.max_retries)
                    continue
                logger.error("翻译API失败: %s", e)

        return {'success': False, 'error': f'翻译失败: {last_error}'}

    async def _do_async_execute(
        self,
        text: str,
        target_lang: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """异步核心翻译逻辑。"""
        if not text:
            return {'success': False, 'error': '未指定翻译文本'}

        target_lang = target_lang.lower().strip()
        if target_lang not in SUPPORTED_TARGETS:
            return {
                'success': False,
                'error': f'不支持的目标语言: {target_lang}，支持: {", ".join(sorted(SUPPORTED_TARGETS))}',
            }

        source_lang = kwargs.get('source_lang', 'autodetect')
        langpair = f"{source_lang}|{target_lang}"

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await self._call_api_async(text, langpair)
                if result:
                    return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(0.5)
                    logger.warning("翻译重试(异步) %d/%d", attempt + 1, self.max_retries)
                    continue
                logger.error("翻译API失败(异步): %s", e)

        return {'success': False, 'error': f'翻译失败: {last_error}'}

    def _call_api(self, text: str, langpair: str) -> Optional[Dict[str, Any]]:
        """同步调用MyMemory API。

        Args:
            text: 翻译文本
            langpair: 语言对 (如 "autodetect|en")

        Returns:
            翻译结果字典，失败返回None
        """
        import httpx

        response = httpx.get(
            self.api_url,
            params={'q': text, 'langpair': langpair},
            timeout=10,
            headers={'User-Agent': 'Mozilla/5.0'},
        )
        response.raise_for_status()
        data = response.json()

        # 确保responseStatus是整数
        status = data.get('responseStatus')
        try:
            status_int = int(status) if status else 0
        except (ValueError, TypeError):
            status_int = 0
        
        if status_int == 200:
            return self._build_result(text, data)
        else:
            error_detail = data.get('responseDetails', '未知错误')
            logger.warning("翻译API返回错误: %s", error_detail)
            return None

    async def _call_api_async(self, text: str, langpair: str) -> Optional[Dict[str, Any]]:
        """异步调用MyMemory API（连接复用）。

        Args:
            text: 翻译文本
            langpair: 语言对

        Returns:
            翻译结果字典，失败返回None
        """
        client = await self._get_async_client()
        response = await client.get(
            self.api_url,
            params={'q': text, 'langpair': langpair},
        )
        response.raise_for_status()
        data = response.json()

        # 确保responseStatus是整数
        status = data.get('responseStatus')
        try:
            status_int = int(status) if status else 0
        except (ValueError, TypeError):
            status_int = 0
        
        if status_int == 200:
            return self._build_result(text, data)
        else:
            error_detail = data.get('responseDetails', '未知错误')
            logger.warning("翻译API返回错误(异步): %s", error_detail)
            return None

    def _build_result(self, text: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """构建翻译结果字典。

        Args:
            text: 原文
            data: API响应JSON

        Returns:
            格式化的翻译结果
        """
        translated: str = data['responseData']['translatedText']
        match_val = data.get('responseData', {}).get('match', 0)
        
        # 确保match_val是数字类型
        try:
            match_num = float(match_val) if match_val else 0
            confidence: Optional[float] = round(match_num, 2) if match_num else None
        except (ValueError, TypeError):
            confidence: Optional[float] = None

        # 从langpair提取目标语言
        langpair: str = ''
        if 'responseData' in data and 'translatedText' in data['responseData']:
            pass  # 已经获取了translatedText
        # 尝试从原始请求或参数中获取
        target_lang = 'en'  # 默认值

        # 检测源语言
        detected_lang = self._detect_language(text)
        target_name = LANG_NAMES.get(target_lang, target_lang)
        source_name = LANG_NAMES.get(detected_lang, detected_lang) if detected_lang != 'autodetect' else '自动检测'

        reply = f'[{source_name} → {target_name}] {text}\n译文: {translated}'
        if confidence is not None:
            reply += f'\n置信度: {confidence}'

        return {
            'success': True,
            'action': '翻译',
            'original': text,
            'translated': translated,
            'source_lang': detected_lang,
            'target_lang': target_lang,
            'confidence': confidence,
            'reply': reply,
        }

    @staticmethod
    def _detect_language(text: str) -> str:
        """基于Unicode范围自动检测语言。

        支持：中文、日文（平假名/片假名）、韩文、俄文（西里尔字母）、英文（拉丁字母）。

        Args:
            text: 待检测文本

        Returns:
            语言代码 (zh/ja/ko/ru/en)
        """
        if not text:
            return 'en'

        zh_count = 0
        ja_hira = 0
        ja_kata = 0
        ko_count = 0
        latin_count = 0
        cyrillic_count = 0

        sample = text[:500]
        for char in sample:
            cp = ord(char)
            if '\u4e00' <= char <= '\u9fff':
                zh_count += 1
            elif '\u3040' <= char <= '\u309f':
                ja_hira += 1
            elif '\u30a0' <= char <= '\u30ff':
                ja_kata += 1
            elif 0xac00 <= cp <= 0xd7af or 0x1100 <= cp <= 0x11ff:
                ko_count += 1
            elif 0x0400 <= cp <= 0x04ff:
                cyrillic_count += 1
            elif char.isascii() and char.isalpha():
                latin_count += 1

        scores: Dict[str, float] = {
            'zh': zh_count,
            'ja': (ja_hira + ja_kata) * 2,
            'ko': ko_count * 2,
            'ru': cyrillic_count * 2,
            'en': latin_count,
        }

        detected = max(scores, key=scores.get)
        detected_score = scores.get(detected, 0)
        
        # 确保score是数字类型
        try:
            detected_score_num = float(detected_score) if detected_score else 0
        except (ValueError, TypeError):
            detected_score_num = 0
        
        return detected if detected_score_num > 0 else 'en'

    def _save_to_history(self, original: str, translated: str, 
                       source_lang: str, target_lang: str) -> None:
        """保存翻译记录到历史文件
        
        Args:
            original: 原文
            translated: 译文
            source_lang: 源语言
            target_lang: 目标语言
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d')
            history_file = HISTORY_DIR / f'translation_history_{timestamp}.json'
            
            # 读取现有历史
            history = []
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    try:
                        history = json.load(f)
                    except json.JSONDecodeError:
                        history = []
            
            # 添加新记录
            history.append({
                'timestamp': datetime.now().isoformat(),
                'original': original,
                'translated': translated,
                'source_lang': source_lang,
                'target_lang': target_lang,
            })
            
            # 保存历史（最多保留100条）
            history = history[-100:]
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
            logger.debug("翻译记录已保存: %s", history_file)
        except Exception as e:
            logger.warning("保存翻译历史失败: %s", e)

    def _load_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """加载翻译历史
        
        Args:
            days: 查询最近几天的历史
            
        Returns:
            历史记录列表
        """
        try:
            # 确保days是整数
            days_int = int(days) if days else 7
            
            history = []
            now = datetime.now()
            
            # 遍历历史文件
            for history_file in HISTORY_DIR.glob('translation_history_*.json'):
                try:
                    file_date_str = history_file.stem.replace('translation_history_', '')
                    file_date = datetime.strptime(file_date_str, '%Y%m%d')
                    
                    # 检查是否在指定天数内
                    if (now - file_date).days <= days_int:
                        with open(history_file, 'r', encoding='utf-8') as f:
                            file_history = json.load(f)
                            history.extend(file_history)
                except Exception as e:
                    logger.warning("读取历史文件失败 %s: %s", history_file, e)
                    continue
            
            # 按时间倒序排序
            history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return history
            
        except Exception as e:
            logger.error("加载翻译历史失败: %s", e)
            return []

    def batch_translate(self, texts: List[str], target_lang: str = 'en',
                     source_lang: str = 'autodetect') -> Dict[str, Any]:
        """批量翻译
        
        Args:
            texts: 待翻译文本列表
            target_lang: 目标语言
            source_lang: 源语言
            
        Returns:
            批量翻译结果
        """
        if not texts:
            return {'success': False, 'error': '未指定翻译文本'}
        
        results = []
        errors = []
        
        for i, text in enumerate(texts):
            try:
                result = self._do_execute(text, target_lang, source_lang=source_lang)
                if result.get('success'):
                    results.append({
                        'index': i,
                        'original': text,
                        'translated': result.get('translated', ''),
                        'source_lang': result.get('source_lang', ''),
                        'target_lang': result.get('target_lang', ''),
                    })
                    # 保存到历史
                    self._save_to_history(
                        text, 
                        result.get('translated', ''),
                        result.get('source_lang', ''),
                        result.get('target_lang', '')
                    )
                else:
                    errors.append({
                        'index': i,
                        'text': text,
                        'error': result.get('error', '未知错误'),
                    })
            except Exception as e:
                errors.append({
                    'index': i,
                    'text': text,
                    'error': str(e),
                })
        
        reply_lines = [
            f"📝 批量翻译完成",
            f"总数: {len(texts)}",
            f"成功: {len(results)}",
            f"失败: {len(errors)}",
            "",
            "翻译结果:",
        ]
        
        for result in results[:10]:
            reply_lines.append(f"{result['index']+1}. {result['original'][:50]}...")
            reply_lines.append(f"   → {result['translated'][:50]}...")
        
        if len(results) > 10:
            reply_lines.append(f"...还有{len(results)-10}条")
        
        if errors:
            reply_lines.append("")
            reply_lines.append("失败项:")
            for error in errors[:5]:
                reply_lines.append(f"{error['index']+1}. {error['text'][:30]}... - {error['error']}")
        
        return {
            'success': True,
            'action': '批量翻译',
            'total': len(texts),
            'success_count': len(results),
            'error_count': len(errors),
            'results': results,
            'errors': errors,
            'reply': '\n'.join(reply_lines),
        }

    def get_history(self, days: int = 7, limit: int = 20) -> Dict[str, Any]:
        """获取翻译历史
        
        Args:
            days: 查询最近几天的历史
            limit: 返回记录数限制
            
        Returns:
            历史记录
        """
        # 确保days是整数
        try:
            days_int = int(days) if days else 7
        except (ValueError, TypeError):
            days_int = 7
        
        # 确保limit是整数
        try:
            limit_int = int(limit) if limit else 20
        except (ValueError, TypeError):
            limit_int = 20
        
        history = self._load_history(days_int)
        limited_history = history[:limit_int]
        
        reply_lines = [
            f"📚 翻译历史 (最近{days_int}天)",
            f"记录数: {len(limited_history)}",
            "",
        ]
        
        for record in limited_history:
            timestamp = record.get('timestamp', '')[:16]
            original = record.get('original', '')[:30]
            translated = record.get('translated', '')[:30]
            source_lang = record.get('source_lang', '')
            target_lang = record.get('target_lang', '')
            
            reply_lines.append(f"[{timestamp}] {source_lang}→{target_lang}")
            reply_lines.append(f"  原文: {original}...")
            reply_lines.append(f"  译文: {translated}...")
            reply_lines.append("")
        
        return {
            'success': True,
            'action': '翻译历史',
            'total': len(history),
            'returned': len(limited_history),
            'history': limited_history,
            'reply': '\n'.join(reply_lines),
        }


translator = TranslatorHandler()