"""
LSP 客户端 — Language Server Protocol 协议实现

支持连接语言服务器，获取代码智能信息
对标 opencode 的 LSP 集成
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LSPConfig:
    """LSP 服务器配置"""
    language: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    root_uri: str = ""


@dataclass
class Position:
    """位置"""
    line: int
    character: int


@dataclass
class Range:
    """范围"""
    start: Position
    end: Position


@dataclass
class Location:
    """位置信息"""
    uri: str
    range: Range


@dataclass
class Diagnostic:
    """诊断信息"""
    range: Range
    severity: int  # 1=Error, 2=Warning, 3=Information, 4=Hint
    message: str
    source: str = ""
    code: str = ""


@dataclass
class CompletionItem:
    """补全项"""
    label: str
    kind: int = 0  # CompletionItemKind
    detail: str = ""
    documentation: str = ""
    insert_text: str = ""


@dataclass
class SymbolInformation:
    """符号信息"""
    name: str
    kind: int  # SymbolKind
    location: Location
    container_name: str = ""


class LSPClient:
    """LSP 客户端"""

    def __init__(self, config: LSPConfig):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._initialized = False

    async def connect(self) -> bool:
        """连接 LSP 服务器"""
        if self.process:
            return True

        try:
            cmd = [self.config.command] + self.config.args
            env = {**os.environ, **self.config.env}

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # 启动响应读取
            asyncio.create_task(self._read_responses())

            # 发送初始化请求
            await self._initialize()

            self._initialized = True
            logger.info(f"LSP 服务器连接成功: {self.config.language}")
            return True
        except Exception as e:
            logger.error(f"连接 LSP 服务器失败: {e}")
            return False

    async def _initialize(self) -> None:
        """发送初始化请求"""
        root_uri = self.config.root_uri or f"file://{os.getcwd()}"

        await self._send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "completion": {
                        "completionItem": {
                            "snippetSupport": True
                        }
                    },
                    "hover": True,
                    "definition": True,
                    "references": True,
                    "documentSymbol": True,
                }
            }
        })

        # 发送 initialized 通知
        await self._send_notification("initialized", {})

    async def _send_request(self, method: str, params: dict) -> Any:
        """发送 JSON-RPC 请求"""
        if not self.process:
            raise RuntimeError("LSP 服务器未连接")

        self._request_id += 1
        request_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        # 创建 Future
        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        # 发送请求
        content = json.dumps(request)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()

        # 等待响应
        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            logger.warning(f"LSP 请求超时: {method}")
            self._pending.pop(request_id, None)
            return None

    async def _send_notification(self, method: str, params: dict) -> None:
        """发送 JSON-RPC 通知"""
        if not self.process:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        content = json.dumps(notification)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()

    async def _read_responses(self) -> None:
        """读取响应"""
        while self.process and self.process.stdout:
            try:
                # 读取 Content-Length（带超时）
                try:
                    header = await asyncio.wait_for(
                        self.process.stdout.readline(),
                        timeout=30
                    )
                except asyncio.TimeoutError:
                    logger.debug("LSP 响应读取超时，继续等待...")
                    continue

                if not header:
                    break

                header_str = header.decode().strip()
                if not header_str:
                    continue

                # 解析 Content-Length
                content_length = 0
                for line in header_str.split("\r\n"):
                    if line.startswith("Content-Length:"):
                        content_length = int(line.split(":")[1].strip())
                        break

                if content_length == 0:
                    continue

                # 读取空行
                await self.process.stdout.readline()

                # 读取内容（带超时）
                try:
                    content = await asyncio.wait_for(
                        self.process.stdout.readexactly(content_length),
                        timeout=30
                    )
                except asyncio.TimeoutError:
                    logger.warning("LSP 内容读取超时")
                    continue

                response = json.loads(content.decode())

                # 处理响应
                if "id" in response:
                    request_id = response["id"]
                    future = self._pending.pop(request_id, None)
                    if future and not future.done():
                        if "error" in response:
                            future.set_exception(RuntimeError(response["error"]))
                        else:
                            future.set_result(response.get("result"))
                else:
                    # 通知，忽略
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"读取 LSP 响应失败: {e}")
                break

    async def completion(self, uri: str, position: Position) -> List[CompletionItem]:
        """获取补全建议"""
        result = await self._send_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": position.line, "character": position.character}
        })

        if not result:
            return []

        items = []
        for item in result.get("items", []):
            items.append(CompletionItem(
                label=item.get("label", ""),
                kind=item.get("kind", 0),
                detail=item.get("detail", ""),
                documentation=item.get("documentation", ""),
                insert_text=item.get("insertText", ""),
            ))

        return items

    async def hover(self, uri: str, position: Position) -> Optional[str]:
        """获取悬停信息"""
        result = await self._send_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": position.line, "character": position.character}
        })

        if not result:
            return None

        contents = result.get("contents", {})
        if isinstance(contents, dict):
            return contents.get("value", "")
        elif isinstance(contents, str):
            return contents
        return None

    async def goto_definition(self, uri: str, position: Position) -> List[Location]:
        """跳转到定义"""
        result = await self._send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": position.line, "character": position.character}
        })

        if not result:
            return []

        locations = []
        for loc in (result if isinstance(result, list) else [result]):
            locations.append(Location(
                uri=loc.get("uri", ""),
                range=Range(
                    start=Position(
                        loc["range"]["start"]["line"],
                        loc["range"]["start"]["character"]
                    ),
                    end=Position(
                        loc["range"]["end"]["line"],
                        loc["range"]["end"]["character"]
                    )
                )
            ))

        return locations

    async def find_references(self, uri: str, position: Position) -> List[Location]:
        """查找引用"""
        result = await self._send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": position.line, "character": position.character},
            "context": {"includeDeclaration": True}
        })

        if not result:
            return []

        locations = []
        for loc in result:
            locations.append(Location(
                uri=loc.get("uri", ""),
                range=Range(
                    start=Position(
                        loc["range"]["start"]["line"],
                        loc["range"]["start"]["character"]
                    ),
                    end=Position(
                        loc["range"]["end"]["line"],
                        loc["range"]["end"]["character"]
                    )
                )
            ))

        return locations

    async def document_symbols(self, uri: str) -> List[SymbolInformation]:
        """获取文档符号"""
        result = await self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri}
        })

        if not result:
            return []

        symbols = []
        for sym in result:
            symbols.append(SymbolInformation(
                name=sym.get("name", ""),
                kind=sym.get("kind", 0),
                location=Location(
                    uri=sym.get("location", {}).get("uri", uri),
                    range=Range(
                        start=Position(
                            sym.get("location", {}).get("range", {}).get("start", {}).get("line", 0),
                            sym.get("location", {}).get("range", {}).get("start", {}).get("character", 0)
                        ),
                        end=Position(
                            sym.get("location", {}).get("range", {}).get("end", {}).get("line", 0),
                            sym.get("location", {}).get("range", {}).get("end", {}).get("character", 0)
                        )
                    )
                ),
                container_name=sym.get("containerName", "")
            ))

        return symbols

    async def disconnect(self) -> None:
        """断开连接"""
        if self.process:
            try:
                await self._send_request("shutdown", {})
                await self._send_notification("exit", {})
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except Exception:
                self.process.kill()

            self.process = None
            self._initialized = False
            logger.info(f"LSP 服务器已断开: {self.config.language}")

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._initialized and self.process is not None


# 默认 LSP 配置
DEFAULT_LSP_CONFIGS = {
    "python": LSPConfig(
        language="python",
        command="pylsp",
        args=[],
    ),
    "javascript": LSPConfig(
        language="javascript",
        command="typescript-language-server",
        args=["--stdio"],
    ),
    "typescript": LSPConfig(
        language="typescript",
        command="typescript-language-server",
        args=["--stdio"],
    ),
    "go": LSPConfig(
        language="go",
        command="gopls",
        args=[],
    ),
    "rust": LSPConfig(
        language="rust",
        command="rust-analyzer",
        args=[],
    ),
}


# 全局 LSP 客户端实例
_lsp_clients: Dict[str, LSPClient] = {}


async def get_lsp_client(language: str) -> Optional[LSPClient]:
    """获取 LSP 客户端实例"""
    if language in _lsp_clients:
        return _lsp_clients[language]

    config = DEFAULT_LSP_CONFIGS.get(language)
    if not config:
        return None

    client = LSPClient(config)
    if await client.connect():
        _lsp_clients[language] = client
        return client
    return None


async def disconnect_all_lsp() -> None:
    """断开所有 LSP 连接"""
    for client in _lsp_clients.values():
        await client.disconnect()
    _lsp_clients.clear()
