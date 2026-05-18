"""
HTTP 客户端工具 - 真正的 HTTP 请求，不是代码生成

支持：
- GET/POST 请求
- 超时控制
- 自动重试
- 文件上传
- JSON 处理
"""

import requests
from typing import Dict, Any, List, Optional, Union
import logging
import time

logger = logging.getLogger(__name__)


class HTTPClient:
    """HTTP 客户端"""

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        headers: Dict[str, str] = None
    ):
        """
        初始化 HTTP 客户端

        Args:
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            headers: 默认请求头
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.default_headers = headers or {}

    def get(
        self,
        url: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        retry: bool = True
    ) -> Dict[str, Any]:
        """
        发送 GET 请求

        Args:
            url: 请求 URL
            params: 查询参数
            headers: 请求头
            retry: 是否重试

        Returns:
            响应结果字典
        """
        return self._make_request(
            'GET',
            url,
            params=params,
            headers=headers,
            retry=retry
        )

    def post(
        self,
        url: str,
        data: Dict[str, Any] = None,
        json: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        retry: bool = True
    ) -> Dict[str, Any]:
        """
        发送 POST 请求

        Args:
            url: 请求 URL
            data: 表单数据
            json: JSON 数据
            headers: 请求头
            retry: 是否重试

        Returns:
            响应结果字典
        """
        return self._make_request(
            'POST',
            url,
            data=data,
            json=json,
            headers=headers,
            retry=retry
        )

    def put(
        self,
        url: str,
        data: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        retry: bool = True
    ) -> Dict[str, Any]:
        """发送 PUT 请求"""
        return self._make_request(
            'PUT',
            url,
            data=data,
            headers=headers,
            retry=retry
        )

    def delete(
        self,
        url: str,
        params: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
        retry: bool = True
    ) -> Dict[str, Any]:
        """发送 DELETE 请求"""
        return self._make_request(
            'DELETE',
            url,
            params=params,
            headers=headers,
            retry=retry
        )

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            url: 请求 URL
            **kwargs: 其他请求参数

        Returns:
            响应结果
        """
        headers = {**self.default_headers, **kwargs.get('headers', {})}

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.timeout,
                    headers=headers,
                    **{k: v for k, v in kwargs.items() if k not in ['headers', 'data', 'json']}
                )

                return {
                    'status': response.status_code,
                    'success': response.ok,
                    'headers': dict(response.headers),
                    'data': self._parse_response(response),
                    'elapsed': response.elapsed.total_seconds()
                }

            except requests.exceptions.Timeout:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (attempt + 1))
                continue

            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay * (attempt + 1))
                continue

    def _parse_response(self, response: requests.Response) -> Any:
        """解析响应数据"""
        content_type = response.headers.get('content-type', '').lower()

        if 'json' in content_type:
            return response.json()
        elif 'text' in content_type:
            return response.text
        else:
            return response.content

    def download_file(
        self,
        url: str,
        save_path: str,
        headers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        下载文件

        Args:
            url: 文件 URL
            save_path: 保存路径
            headers: 请求头

        Returns:
            下载结果
        """
        try:
            headers = {**self.default_headers, **headers}
            response = requests.get(url, headers=headers, timeout=self.timeout, stream=True)

            if not response.ok:
                raise Exception(f"下载失败: {response.status_code}")

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return {
                'success': True,
                'file_path': save_path,
                'status': response.status_code,
                'size': os.path.getsize(save_path)
            }

        except Exception as e:
            logger.error(f"下载文件失败 {url}: {e}")
            return {
                'success': False,
                'error': str(e),
                'url': url
            }


# 创建全局 HTTP 客户端实例
http_client = HTTPClient()


def http_get(
    url: str,
    params: Dict[str, Any] = None,
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """HTTP GET 请求（使用全局客户端）"""
    return http_client.get(url, params=params, headers=headers)


def http_post(
    url: str,
    data: Dict[str, Any] = None,
    json: Dict[str, Any] = None,
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """HTTP POST 请求（使用全局客户端）"""
    return http_client.post(url, data=data, json=json, headers=headers)


def http_put(
    url: str,
    data: Dict[str, Any] = None,
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """HTTP PUT 请求（使用全局客户端）"""
    return http_client.put(url, data=data, headers=headers)


def http_delete(
    url: str,
    params: Dict[str, Any] = None,
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """HTTP DELETE 请求（使用全局客户端）"""
    return http_client.delete(url, params=params, headers=headers)


def download_file(url: str, save_path: str, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """下载文件（使用全局客户端）"""
    return http_client.download_file(url, save_path, headers)


# 导出工具
__all__ = [
    'HTTPClient',
    'http_client',
    'http_get',
    'http_post',
    'http_put',
    'http_delete',
    'download_file',
]
