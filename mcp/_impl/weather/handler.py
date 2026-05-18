"""天气查询处理器（工业级 v3.3.0）

基于wttr.in免费API，无需API Key。
支持：当前天气查询、未来3天预报、内存缓存优化。

依赖：httpx
"""

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 类型别名
WeatherData = Dict[str, Any]
ForecastDay = Dict[str, str]


class WeatherHandler:
    """天气查询处理器。

    工业级特性：
    - 同步/异步双接口
    - 内存缓存：同一城市1小时内不重复请求
    - httpx连接复用（异步客户端单例）
    - 完整天气字段：温度/体感/湿度/风速/风向/紫外线/能见度/气压/云量
    - 未来3天预报支持

    Attributes:
        api_url: wttr.in API基础URL
        _cache_ttl: 缓存生存时间（秒）
        _async_client: httpx异步客户端（延迟初始化）
    """

    def __init__(self, cache_ttl: int = 3600) -> None:
        """初始化天气查询处理器。

        Args:
            cache_ttl: 缓存生存时间（秒），默认3600（1小时）
        """
        self.api_url: str = "https://wttr.in"
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl: int = cache_ttl
        self._async_client: Optional[Any] = None
        logger.info("WeatherHandler 初始化完成, 缓存TTL: %ds", cache_ttl)

    async def _get_async_client(self) -> Any:
        """获取或创建httpx异步客户端（懒加载单例）。

        Returns:
            httpx.AsyncClient 实例
        """
        if self._async_client is None or self._async_client.is_closed:
            import httpx
            self._async_client = httpx.AsyncClient(
                headers={'User-Agent': 'curl/7.68.0'},
                timeout=10,
            )
        return self._async_client

    async def close(self) -> None:
        """关闭异步客户端连接。"""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
            self._async_client = None
            logger.debug("WeatherHandler 异步客户端已关闭")

    def execute(self, city: str = '北京', **kwargs: Any) -> Dict[str, Any]:
        """查询天气（同步接口）。

        Args:
            city: 城市名称（中文或英文）
            forecast: 是否获取未来3天预报 (True/False)

        Returns:
            Dict[str, Any]: 包含天气数据的字典
        """
        start_time = time.perf_counter()
        try:
            result = self._do_execute(city, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.info("天气查询完成 [%s], 耗时: %.3fs, 缓存: %s",
                        city, elapsed, result.get('_from_cache', False))
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("天气查询异常 [%s]: %s", city, e, exc_info=True)
            return {'success': False, 'error': f'天气查询异常: {e}'}

    async def aexecute(self, city: str = '北京', **kwargs: Any) -> Dict[str, Any]:
        """查询天气（异步接口）。

        使用httpx异步客户端，连接复用。

        Args:
            city: 城市名称
            forecast: 是否获取预报

        Returns:
            Dict[str, Any]: 天气数据
        """
        start_time = time.perf_counter()
        try:
            result = await self._do_async_execute(city, **kwargs)
            elapsed = time.perf_counter() - start_time
            logger.info("天气查询完成(异步) [%s], 耗时: %.3fs", city, elapsed)
            result.setdefault('_elapsed', round(elapsed, 3))
            return result
        except Exception as e:
            logger.error("天气查询异常(异步) [%s]: %s", city, e, exc_info=True)
            return {'success': False, 'error': f'天气查询异常: {e}'}

    def _do_execute(self, city: str, **kwargs: Any) -> Dict[str, Any]:
        """同步执行核心逻辑。"""
        if not city:
            return {'success': False, 'error': '未指定城市名称'}
        forecast = kwargs.get('forecast', False)

        cached = self._cache.get(city)
        if cached and (time.time() - cached['timestamp']) < self._cache_ttl:
            logger.debug("天气缓存命中: %s", city)
            data = cached['data']
        else:
            data = self._fetch_weather(city)
            if data is None:
                return {'success': False, 'error': '天气数据获取失败'}
            self._cache[city] = {'data': data, 'timestamp': time.time()}

        if forecast:
            return self._parse_forecast(city, data)
        return self._parse_current(city, data)

    async def _do_async_execute(self, city: str, **kwargs: Any) -> Dict[str, Any]:
        """异步执行核心逻辑。"""
        if not city:
            return {'success': False, 'error': '未指定城市名称'}
        forecast = kwargs.get('forecast', False)

        cached = self._cache.get(city)
        if cached and (time.time() - cached['timestamp']) < self._cache_ttl:
            data = cached['data']
        else:
            data = await self._fetch_weather_async(city)
            if data is None:
                return {'success': False, 'error': '天气数据获取失败'}
            self._cache[city] = {'data': data, 'timestamp': time.time()}

        if forecast:
            return self._parse_forecast(city, data)
        return self._parse_current(city, data)

    def _fetch_weather(self, city: str) -> Optional[Dict[str, Any]]:
        """同步获取天气数据。

        Args:
            city: 城市名称

        Returns:
            API响应JSON字典，失败返回None
        """
        try:
            import httpx
            response = httpx.get(
                f"{self.api_url}/{city}",
                params={'format': 'j1', 'lang': 'zh'},
                timeout=10,
                headers={'User-Agent': 'curl/7.68.0'},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("天气API请求失败 [%s]: %s", city, e)
            return None

    async def _fetch_weather_async(self, city: str) -> Optional[Dict[str, Any]]:
        """异步获取天气数据（连接复用）。

        Args:
            city: 城市名称

        Returns:
            API响应JSON字典，失败返回None
        """
        try:
            client = await self._get_async_client()
            response = await client.get(
                f"{self.api_url}/{city}",
                params={'format': 'j1', 'lang': 'zh'},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("天气API请求失败(异步) [%s]: %s", city, e)
            return None

    def _parse_current(self, city: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析当前天气数据。

        Args:
            city: 城市名称
            data: wttr.in API响应数据

        Returns:
            格式化的天气数据字典
        """
        current = data.get('current_condition', [{}])[0]

        desc_list = current.get('lang_zh', current.get('weatherDesc', [{}]))
        desc: str = desc_list[0].get('value', '未知') if desc_list else '未知'

        temp: str = current.get('temp_C', 'N/A')
        feels_like: str = current.get('FeelsLikeC', 'N/A')
        humidity: str = current.get('humidity', 'N/A')
        wind_speed: str = current.get('windspeedKmph', 'N/A')
        wind_dir: str = current.get('winddir16Point', '')
        uv_index: str = current.get('uvIndex', 'N/A')
        visibility: str = current.get('visibility', 'N/A')
        pressure: str = current.get('pressure', 'N/A')
        cloud_cover: str = current.get('cloudcover', 'N/A')

        aqi_info: str = ''
        aqi = current.get('air_quality', '')
        if aqi and isinstance(aqi, dict):
            aqi_val = aqi.get('gb-defra-index', 'N/A')
            aqi_info = f"，空气质量指数: {aqi_val}"

        reply = (
            f'🌍 {city}天气\n'
            f'天气: {desc}\n'
            f'气温: {temp}°C（体感 {feels_like}°C）\n'
            f'湿度: {humidity}%\n'
            f'风速: {wind_speed}km/h {wind_dir}\n'
            f'紫外线: {uv_index}\n'
            f'能见度: {visibility}km\n'
            f'气压: {pressure}hPa\n'
            f'云量: {cloud_cover}%'
            f'{aqi_info}'
        )

        return {
            'success': True,
            'action': '当前天气',
            'city': city,
            'weather': desc,
            'temperature': f'{temp}°C',
            'feels_like': f'{feels_like}°C',
            'humidity': f'{humidity}%',
            'wind_speed': f'{wind_speed}km/h',
            'wind_direction': wind_dir,
            'uv_index': uv_index,
            'visibility': f'{visibility}km',
            'pressure': f'{pressure}hPa',
            'cloud_cover': f'{cloud_cover}%',
            'aqi': aqi_info.strip('，'),
            'reply': reply,
        }

    def _parse_forecast(self, city: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析未来3天天气预报。

        Args:
            city: 城市名称
            data: wttr.in API响应数据

        Returns:
            包含预报列表的字典
        """
        forecast_list: List[Dict[str, Any]] = data.get('weather', [])[:3]
        if not forecast_list:
            return {'success': False, 'error': '无法获取预报数据'}

        days: List[ForecastDay] = []
        for day_data in forecast_list:
            date: str = day_data.get('date', '')
            max_temp: str = day_data.get('maxtempC', 'N/A')
            min_temp: str = day_data.get('mintempC', 'N/A')

            hourly = day_data.get('hourly', [{}])
            noon = hourly[len(hourly) // 2] if hourly else {}
            desc_list = noon.get('lang_zh', noon.get('weatherDesc', [{}]))
            desc: str = desc_list[0].get('value', '未知') if desc_list else '未知'

            days.append({
                'date': date,
                'weather': desc,
                'max_temp': f'{max_temp}°C',
                'min_temp': f'{min_temp}°C',
                'humidity': f'{noon.get("humidity", "N/A")}%',
                'wind_speed': f'{noon.get("windspeedKmph", "N/A")}km/h',
                'wind_direction': noon.get('winddir16Point', ''),
                'uv_index': noon.get('uvIndex', 'N/A'),
            })

        lines: List[str] = [f'🌍 {city} 未来天气预报']
        for day in days:
            lines.append(
                f'\n📅 {day["date"]}\n'
                f'  {day["weather"]}\n'
                f'  温度: {day["min_temp"]} ~ {day["max_temp"]}\n'
                f'  湿度: {day["humidity"]}, 风速: {day["wind_speed"]} {day["wind_direction"]}\n'
                f'  紫外线: {day["uv_index"]}'
            )

        current = data.get('current_condition', [{}])[0]
        current_temp: str = current.get('temp_C', 'N/A')

        return {
            'success': True,
            'action': '天气预报',
            'city': city,
            'current_temp': f'{current_temp}°C',
            'forecast': days,
            'reply': '\n'.join(lines),
        }


weather_handler = WeatherHandler()
