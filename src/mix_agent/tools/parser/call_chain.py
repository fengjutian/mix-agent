"""函数调用链追踪器 — AST 深度遍历，追踪 Route → Service → DAO → DB 路径。"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CallNode:
    """调用链中的一个节点。"""
    name: str
    file_path: str
    line_number: int
    kind: str  # "route" | "service" | "dao" | "db" | "function"
    calls: list[str] = field(default_factory=list)  # 该节点调用的其他函数
    is_async: bool = False


@dataclass
class CallChain:
    """一条完整的调用链。"""
    entry_point: str          # 路由处理函数名
    file_path: str
    chain: list[str]          # 调用链上的函数名序列
    depth: int
    reaches_db: bool = False   # 是否最终触达数据库操作


@dataclass
class CallGraphResult:
    """调用图分析结果。"""
    chains: list[CallChain] = field(default_factory=list)
    nodes: dict[str, CallNode] = field(default_factory=dict)
    db_operations: list[dict] = field(default_factory=list)


class CallChainTracer:
    """函数调用链追踪器。

    通过 AST 深度遍历，追踪从路由处理函数出发，经过哪些 Service/DAO 层，
    最终是否触达数据库操作（SQLAlchemy session、raw SQL 等）。
    """

    # 认为是数据库操作的函数/方法名
    DB_OPERATIONS = {
        "execute", "executemany", "commit", "rollback", "flush",
        "session.execute", "session.add", "session.delete", "session.query",
        "select", "insert", "update", "delete",  # SQLAlchemy Core
        "text",  # SQLAlchemy text()
    }

    # 认为是 Service 层的命名模式
    SERVICE_PATTERNS = ["service", "Service", "manager", "Manager"]

    # 认为是 DAO/Repository 层的命名模式
    DAO_PATTERNS = ["dao", "DAO", "repository", "Repository", "repo", "Repo"]

    def __init__(self):
        self._call_graph: dict[str, set[str]] = {}  # func_name → {called_funcs}
        self._func_locations: dict[str, dict] = {}   # func_name → {file, line, kind}

    # ── 公开 API ──

    def trace_from_routes(
        self, routes: list, source_root: str | Path = "."
    ) -> CallGraphResult:
        """从路由列表出发，追踪每个 handler 的调用链。

        Args:
            routes: RouteInfo 列表（从 RouteScanner 获取）
            source_root: 源码根目录

        Returns:
            CallGraphResult: 含所有调用链和节点信息
        """
        root = Path(source_root)
        # 先扫描所有 .py 文件建立函数调用图
        self._build_call_graph(root)

        result = CallGraphResult()
        result.nodes = self._func_locations.copy()

        for route in routes:
            handler = route.handler
            chain = self._trace_from(handler, visited=set(), max_depth=10)
            if chain:
                reaches_db = any(
                    any(db_op in node_name.lower() for db_op in self.DB_OPERATIONS)
                    for node_name in chain
                )
                result.chains.append(CallChain(
                    entry_point=f"{route.method} {route.path}",
                    file_path=route.file_path,
                    chain=chain,
                    depth=len(chain),
                    reaches_db=reaches_db,
                ))

        # 收集数据库操作
        for name, node in self._func_locations.items():
            if node["kind"] in ("db", "dao"):
                result.db_operations.append(node)

        return result

    def trace_from_function(self, func_name: str, source_root: str | Path = ".") -> list[str]:
        """从指定函数出发追踪调用链。"""
        self._build_call_graph(Path(source_root))
        return self._trace_from(func_name, visited=set(), max_depth=10)

    # ── 内部实现 ──

    def _build_call_graph(self, root: Path) -> None:
        """扫描目录下所有 .py 文件，建立函数调用图。"""
        for py_file in root.rglob("*.py"):
            if "__pycache__" in str(py_file) or "node_modules" in str(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
                self._scan_file(tree, str(py_file))
            except (SyntaxError, OSError):
                pass

    def _scan_file(self, tree: ast.Module, file_path: str) -> None:
        """扫描单个文件，提取函数定义和调用关系。"""
        # 第一遍：收集所有函数定义
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if name.startswith("_"):
                    continue  # 跳过私有函数
                kind = self._classify_function(name, file_path)
                self._func_locations[name] = {
                    "name": name,
                    "file_path": file_path,
                    "line_number": node.lineno,
                    "kind": kind,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }
                if name not in self._call_graph:
                    self._call_graph[name] = set()

                # 提取函数体内的调用
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        called = self._name_of(child.func)
                        if called and not called.startswith("_"):
                            self._call_graph[name].add(called)

    def _classify_function(self, name: str, file_path: str) -> str:
        """根据函数名和文件路径分类为 route/service/dao/db/function。"""
        lower_path = file_path.lower()
        lower_name = name.lower()

        # 路径判断
        if "route" in lower_path or "api" in lower_path or "controller" in lower_path:
            return "route"
        if any(p in lower_path for p in self.DAO_PATTERNS):
            return "dao"
        if any(p in lower_path for p in self.SERVICE_PATTERNS):
            return "service"
        if "model" in lower_path or "db" in lower_path:
            return "db"

        # 名称判断
        if any(p in lower_name for p in self.DAO_PATTERNS):
            return "dao"
        if any(p in lower_name for p in self.SERVICE_PATTERNS):
            return "service"

        return "function"

    def _trace_from(self, func_name: str, visited: set, max_depth: int) -> list[str]:
        """DFS 追踪调用链，返回函数名列表。"""
        if func_name in visited or max_depth <= 0:
            return [func_name] if func_name not in visited else []

        visited.add(func_name)
        chain = [func_name]

        callees = self._call_graph.get(func_name, set())
        for callee in sorted(callees):
            sub_chain = self._trace_from(callee, visited.copy(), max_depth - 1)
            chain.extend(sub_chain)
            if len(chain) > 20:  # 截断
                chain.append("...")
                break

        return chain

    def _name_of(self, node: ast.AST | None) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr  # 只取最后一级属性
        if isinstance(node, ast.Call):
            return self._name_of(node.func)
        return ""
