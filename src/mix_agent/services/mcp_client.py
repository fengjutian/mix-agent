"""MCP 协议客户端 — JSON-RPC 2.0 over stdio / http / sse。

支持：
- initialize 握手
- tools/list 工具发现
- tools/call 工具调用
- 连接测试
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field

import httpx

from mix_agent.services.mcp_store import MCPServerConfig


# ── JSON-RPC 2.0 消息 ──

@dataclass
class JSONRPCRequest:
    method: str
    params: dict | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict:
        d: dict = {"jsonrpc": self.jsonrpc, "method": self.method, "id": self.id}
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass
class JSONRPCResponse:
    id: str
    result: dict | None = None
    error: dict | None = None
    jsonrpc: str = "2.0"

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def from_dict(cls, d: dict) -> JSONRPCResponse:
        return cls(
            id=d.get("id", ""),
            result=d.get("result"),
            error=d.get("error"),
            jsonrpc=d.get("jsonrpc", "2.0"),
        )


# ── 错误 ──

class MCPError(Exception):
    """MCP 协议错误。"""
    def __init__(self, message: str, code: int = -1):
        super().__init__(message)
        self.code = code


class MCPConnectionError(MCPError):
    """连接失败。"""


class MCPTimeoutError(MCPError):
    """超时。"""


# ── stdio 传输 ──

class StdioTransport:
    """通过子进程 stdin/stdout 通信的 MCP 传输层。"""

    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self._process: subprocess.Popen | None = None

    async def connect(self, timeout: float = 10.0) -> None:
        merged_env = {**os.environ, **self.env}
        try:
            self._process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=merged_env,
                text=True,
            )
        except FileNotFoundError:
            raise MCPConnectionError(f"Command not found: {self.command}")
        except Exception as e:
            raise MCPConnectionError(str(e))

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._process or not self._process.stdin:
            raise MCPConnectionError("Not connected")
        payload = json.dumps(request.to_dict()) + "\n"
        self._process.stdin.write(payload)
        self._process.stdin.flush()
        # 读取一行 JSON 响应
        if not self._process.stdout:
            raise MCPConnectionError("No stdout")
        line = self._process.stdout.readline()
        if not line:
            raise MCPConnectionError("No response from server")
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            raise MCPError(f"Invalid JSON response: {line[:200]}")
        return JSONRPCResponse.from_dict(data)

    async def disconnect(self) -> None:
        if self._process:
            try:
                self._process.stdin.close()
                self._process.stdout.close()  # type: ignore
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None


# ── HTTP 传输 ──

class HTTPTransport:
    """通过 HTTP POST 通信的 MCP 传输层（Streamable HTTP）。"""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    async def connect(self, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._client:
            raise MCPConnectionError("Not connected")
        try:
            resp = await self._client.post(
                self.url,
                json=request.to_dict(),
                headers={**self.headers, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            raise MCPTimeoutError(f"Request to {self.url} timed out")
        except httpx.HTTPError as e:
            raise MCPConnectionError(str(e))
        return JSONRPCResponse.from_dict(data)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ── SSE 传输（简化：post + SSE 读取） ──

class SSETransport:
    """通过 HTTP POST + SSE 事件流通信的 MCP 传输层。"""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None

    async def connect(self, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._client:
            raise MCPConnectionError("Not connected")
        try:
            headers = {**self.headers, "Content-Type": "application/json"}
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id

            resp = await self._client.post(
                self.url,
                json=request.to_dict(),
                headers=headers,
            )
            resp.raise_for_status()

            # 获取 session id
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self._session_id = sid

            # SSE 响应体可能是 text/event-stream
            ct = resp.headers.get("content-type", "")
            if "text/event-stream" in ct:
                data = _parse_sse(resp.text)
            else:
                data = resp.json()
        except httpx.TimeoutException:
            raise MCPTimeoutError(f"Request to {self.url} timed out")
        except httpx.HTTPError as e:
            raise MCPConnectionError(str(e))
        return JSONRPCResponse.from_dict(data)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._session_id = None


def _parse_sse(text: str) -> dict:
    """从 SSE 事件流中提取 data 字段 JSON。"""
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise MCPError("No data event in SSE response")


# ── 传输工厂 ──

def _create_transport(cfg: MCPServerConfig):
    if cfg.transport == "stdio":
        return StdioTransport(cfg.command, cfg.args, cfg.env)
    elif cfg.transport == "http":
        return HTTPTransport(cfg.url, cfg.headers)
    elif cfg.transport == "sse":
        return SSETransport(cfg.url, cfg.headers)
    else:
        raise MCPError(f"Unknown transport: {cfg.transport}")


# ── MCP 客户端 ──

@dataclass
class MCPToolInfo:
    """MCP 工具元信息。"""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


@dataclass
class MCPTestResult:
    """连接测试结果。"""
    ok: bool
    server_name: str
    server_version: str = ""
    tools: list[MCPToolInfo] = field(default_factory=list)
    error: str = ""


class MCPClient:
    """MCP 协议客户端。

    使用方式：
        client = MCPClient(config)
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("tool_name", {"arg": "value"})
        await client.disconnect()
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._transport = _create_transport(config)
        self._server_name = ""
        self._server_version = ""
        self._connected = False

    async def connect(self) -> None:
        """建立连接并完成 initialize 握手。"""
        await self._transport.connect()

        # initialize
        init_req = JSONRPCRequest(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mix-agent", "version": "0.1.0"},
            },
        )
        resp = await self._transport.send(init_req)
        if not resp.ok:
            raise MCPError(
                f"Initialize failed: {resp.error}",
                code=resp.error.get("code", -1) if resp.error else -1,
            )

        result = resp.result or {}
        self._server_name = result.get("serverInfo", {}).get("name", "")
        self._server_version = result.get("serverInfo", {}).get("version", "")
        self._connected = True

        # 发送 initialized 通知（JSON-RPC 通知无 id）
        notif = JSONRPCRequest(method="notifications/initialized", id="")
        await self._transport.send(notif)

    async def list_tools(self) -> list[MCPToolInfo]:
        """获取服务器提供的工具列表。"""
        req = JSONRPCRequest(method="tools/list")
        resp = await self._transport.send(req)
        if not resp.ok:
            raise MCPError(
                f"tools/list failed: {resp.error}",
                code=resp.error.get("code", -1) if resp.error else -1,
            )
        tools = []
        for t in (resp.result or {}).get("tools", []):
            tools.append(MCPToolInfo(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            ))
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用指定工具。"""
        req = JSONRPCRequest(
            method="tools/call",
            params={"name": name, "arguments": arguments},
        )
        resp = await self._transport.send(req)
        if not resp.ok:
            raise MCPError(
                f"tools/call failed: {resp.error}",
                code=resp.error.get("code", -1) if resp.error else -1,
            )
        return resp.result or {}

    async def disconnect(self) -> None:
        self._connected = False
        await self._transport.disconnect()

    async def test_connection(self) -> MCPTestResult:
        """快速测试连接并返回工具列表。"""
        try:
            await self.connect()
            tools = await self.list_tools()
            return MCPTestResult(
                ok=True,
                server_name=self._server_name,
                server_version=self._server_version,
                tools=tools,
            )
        except MCPError as e:
            return MCPTestResult(
                ok=False,
                server_name="",
                error=str(e),
            )
        except Exception as e:
            return MCPTestResult(
                ok=False,
                server_name="",
                error=f"Unexpected error: {e}",
            )
        finally:
            try:
                await self.disconnect()
            except Exception:
                pass
