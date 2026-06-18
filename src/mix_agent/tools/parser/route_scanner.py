"""FastAPI 路由扫描器 — AST 深度分析，提取所有 HTTP 端点、中间件和鉴权信息。"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RouteInfo:
    """单条路由信息。"""
    method: str              # GET / POST / PUT / DELETE / PATCH
    path: str
    handler: str             # 处理函数名
    file_path: str
    line_number: int
    has_auth: bool = False   # 是否包含 Depends(get_current_user) 等鉴权
    auth_deps: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class RouteScanResult:
    """路由扫描结果。"""
    routes: list[RouteInfo] = field(default_factory=list)
    routers: list[dict] = field(default_factory=list)  # APIRouter 注册信息
    unauthenticated_routes: list[RouteInfo] = field(default_factory=list)
    total_endpoints: int = 0


class RouteScanner:
    """FastAPI 路由扫描器。

    扫描 Python 源码中的：
    - @app.get/post/put/delete/patch 装饰器
    - @router.get/post/... 装饰器（APIRouter）
    - app.include_router(...) 注册
    - Depends(get_current_user) 等鉴权依赖
    """

    # HTTP 方法装饰器名
    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

    # 鉴权依赖函数名（可扩展）
    AUTH_DEPS = {
        "get_current_user", "require_admin", "require_auditor",
        "require_developer", "require_role",
    }

    def __init__(self):
        pass

    # ── 公开 API ──

    def scan_file(self, file_path: str | Path) -> RouteScanResult:
        """扫描单个文件。"""
        path = Path(file_path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        return self._scan_tree(tree, str(path))

    def scan_files(self, file_paths: list[str | Path]) -> dict[str, RouteScanResult]:
        """批量扫描多个文件。"""
        results: dict[str, RouteScanResult] = {}
        for fp in file_paths:
            try:
                results[str(fp)] = self.scan_file(fp)
            except (SyntaxError, OSError) as e:
                results[str(fp)] = RouteScanResult()
        return results

    def scan_directory(self, root: str | Path = ".") -> RouteScanResult:
        """递归扫描目录下所有 .py 文件。"""
        root_path = Path(root)
        merged = RouteScanResult()

        for py_file in root_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            result = self.scan_file(py_file)
            merged.routes.extend(result.routes)
            merged.routers.extend(result.routers)
            merged.unauthenticated_routes.extend(result.unauthenticated_routes)
            merged.total_endpoints += result.total_endpoints

        return merged

    # ── 内部实现 ──

    def _scan_tree(self, tree: ast.Module, file_path: str) -> RouteScanResult:
        result = RouteScanResult()

        for node in ast.walk(tree):
            # 检测 @app.get(...) / @router.post(...) 装饰器
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    route = self._parse_decorator(decorator, node, file_path)
                    if route:
                        result.routes.append(route)
                        result.total_endpoints += 1
                        if not route.has_auth:
                            result.unauthenticated_routes.append(route)

            # 检测 app.include_router(...)
            if isinstance(node, ast.Call):
                if self._is_include_router(node):
                    result.routers.append(self._parse_include_router(node))

        return result

    def _parse_decorator(
        self, decorator: ast.AST, func: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str
    ) -> RouteInfo | None:
        """解析路由装饰器，提取 method/path/auth 信息。"""
        # 处理 @app.get("/path") 或 @router.post("/path")
        call = decorator
        if isinstance(call, ast.Call):
            # 检查是否是 method 调用: app.get(...) or router.post(...)
            method = self._get_method_name(call.func)
            if method not in self.HTTP_METHODS:
                return None

            # 提取 path
            path = "/"
            if call.args:
                first_arg = call.args[0]
                if isinstance(first_arg, ast.Constant):
                    path = str(first_arg.value)

            # 检查函数体是否包含鉴权依赖
            has_auth, auth_deps = self._check_auth(func)

            # 提取 tags/summary 等关键字参数
            tags: list[str] = []
            summary = ""
            for kw in call.keywords:
                if kw.arg == "tags" and isinstance(kw.value, ast.List):
                    tags = [
                        e.value if isinstance(e, ast.Constant) else ""
                        for e in kw.value.elts
                    ]
                elif kw.arg == "summary" and isinstance(kw.value, ast.Constant):
                    summary = str(kw.value.value)

            return RouteInfo(
                method=method.upper(),
                path=path,
                handler=func.name,
                file_path=file_path,
                line_number=func.lineno,
                has_auth=has_auth,
                auth_deps=auth_deps,
                tags=tags,
                summary=summary,
            )

        return None

    def _get_method_name(self, node: ast.AST) -> str | None:
        """提取方法名: app.get → 'get', router.post → 'post'"""
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _check_auth(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, list[str]]:
        """检查函数参数是否包含鉴权依赖。"""
        auth_deps: list[str] = []
        for arg in func.args.args:
            # 检查类型注解中是否包含 Depends(get_current_user)
            if arg.annotation and isinstance(arg.annotation, ast.Subscript):
                # 可能是 Optional[...] 或其他泛型，跳过
                pass
            if arg.annotation and isinstance(arg.annotation, ast.Call):
                if self._name_of(arg.annotation.func) == "Depends":
                    dep_name = self._name_of(arg.annotation.args[0]) if arg.annotation.args else ""
                    auth_deps.append(dep_name)

        # 检查函数体内的 Depends 调用
        if not auth_deps:
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and self._name_of(node.func) == "Depends":
                    if node.args:
                        dep_name = self._name_of(node.args[0])
                        if dep_name in self.AUTH_DEPS:
                            auth_deps.append(dep_name)

        return len(auth_deps) > 0, auth_deps

    def _is_include_router(self, node: ast.Call) -> bool:
        """检测 app.include_router(...) 调用。"""
        return self._name_of(node.func) in ("include_router",)

    def _parse_include_router(self, node: ast.Call) -> dict:
        """解析 include_router 调用信息。"""
        info: dict = {"router": "", "prefix": "", "tags": []}
        if node.args:
            info["router"] = self._name_of(node.args[0])
        for kw in node.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                info["prefix"] = str(kw.value.value)
            elif kw.arg == "tags" and isinstance(kw.value, ast.List):
                info["tags"] = [
                    e.value if isinstance(e, ast.Constant) else ""
                    for e in kw.value.elts
                ]
        return info

    def _name_of(self, node: ast.AST | None) -> str:
        """AST 节点 → 可读名称。"""
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._name_of(node.value)}.{node.attr}"
        if isinstance(node, ast.Constant):
            return str(node.value)
        return type(node).__name__
