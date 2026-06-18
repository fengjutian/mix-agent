"""接口调用链分析 API — 输入接口路径，分析代码调用过程、涉及的表，生成泳道图。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mix_agent.tools.parser.route_scanner import RouteScanner
from mix_agent.tools.parser.call_chain import CallChainTracer
from mix_agent.tools.parser.table_extractor import TableExtractor
from mix_agent.tools.parser.swimlane_builder import build_swimlane

router = APIRouter()

# ── 请求/响应模型 ──


class TraceRequest(BaseModel):
    """调用链追踪请求。"""
    method: str = Field(..., description="HTTP 方法 (GET/POST/PUT/DELETE/PATCH)")
    path: str = Field(..., description="接口路径，如 /api/v1/admin/cost/overview")
    source_root: str = Field(default=".", description="源码根目录，默认当前目录")


class NodeInfo(BaseModel):
    """调用链节点。"""
    name: str
    kind: str
    file_path: str = ""
    line_number: int = 0


class TableRef(BaseModel):
    """表引用信息。"""
    table_name: str
    class_name: str | None = None
    operation: str = "UNKNOWN"
    location: str = ""
    file_path: str = ""
    line_number: int = 0


class TraceResponse(BaseModel):
    """调用链追踪响应。"""
    ok: bool = True
    entry_point: str = ""
    route_info: dict | None = None
    call_chain: list[NodeInfo] = []
    tables: list[TableRef] = []
    swimlane: str = ""            # Mermaid 泳道图代码
    diagram_nodes: list[dict] = []
    diagram_edges: list[dict] = []
    summary: str = ""
    all_routes: list[dict] = []   # 可供搜索的所有路由列表
    error: str = ""


class ListRoutesResponse(BaseModel):
    """路由列表响应。"""
    ok: bool = True
    routes: list[dict] = []
    total: int = 0


# ── 工具函数 ──



# ── 路由：获取所有接口列表 ──


@router.get("/routes")
def list_routes(
    source_root: str = ".",
) -> ListRoutesResponse:
    """列出项目所有已注册的 API 路由，供前端下拉选择。

    自动拼接 router prefix，返回完整路径（如 /api/v1/admin/cost/overview）。
    """
    scanner = RouteScanner()
    result = scanner.scan_directory(source_root)

    # 构建文件名前缀映射：从 include_router 调用中提取 prefix
    file_prefix_map: dict[str, str] = {}
    for rinfo in result.routers:
        router_name = rinfo.get("router", "")
        prefix = rinfo.get("prefix", "")
        if router_name and prefix:
            file_prefix_map[router_name] = prefix

    # 构建文件名 → prefix 的模糊映射（用于无精确匹配时的回退）
    def _guess_prefix(file_path: str) -> str:
        file_stem = Path(file_path).stem  # e.g. "v1_admin"
        for rname, pfx in file_prefix_map.items():
            # rname like "admin_router" or "tasks_router"
            core = rname.replace("_router", "")
            if core in file_stem or file_stem in core:
                return pfx
        # 回退：按 tags 匹配
        return ""

    routes = []
    for r in result.routes:
        prefix = _guess_prefix(r.file_path)
        full_path = prefix + r.path if prefix else r.path
        # 避免双斜杠
        full_path = full_path.replace("//", "/")
        routes.append({
            "method": r.method,
            "path": r.path,
            "full_path": full_path,
            "handler": r.handler,
            "file_path": r.file_path,
            "line_number": r.line_number,
            "has_auth": r.has_auth,
            "tags": r.tags,
            "summary": r.summary,
        })

    # 按方法 + 完整路径排序
    routes.sort(key=lambda r: (r["method"], r["full_path"]))

    return ListRoutesResponse(
        ok=True,
        routes=routes,
        total=len(routes),
    )


# ── 路由：分析接口调用链 ──


@router.post("/trace")
def trace_interface(
    body: TraceRequest,
) -> TraceResponse:
    """分析指定接口的代码调用链，生成泳道图。

    输入接口路径（如 POST /api/v1/tasks/），系统会：
    1. 定位路由处理函数
    2. 追踪函数调用链（Route → Service → DAO → DB）
    3. 检测涉及的数据库表
    4. 生成 Mermaid 泳道图
    """
    method = body.method.upper().strip()
    path = body.path.strip()
    source_root = body.source_root

    if not method or not path:
        return TraceResponse(ok=False, error="请提供 method 和 path 参数")

    # 1. 扫描所有路由，供前端参考
    scanner = RouteScanner()
    scan_result = scanner.scan_directory(source_root)

    # 构建前缀映射
    file_prefix_map: dict[str, str] = {}
    for rinfo in scan_result.routers:
        router_name = rinfo.get("router", "")
        prefix = rinfo.get("prefix", "")
        if router_name and prefix:
            file_prefix_map[router_name] = prefix

    def _guess_prefix(file_path: str) -> str:
        file_stem = Path(file_path).stem
        for rname, pfx in file_prefix_map.items():
            core = rname.replace("_router", "")
            if core in file_stem or file_stem in core:
                return pfx
        return ""

    all_routes = [
        {
            "method": r.method,
            "path": r.path,
            "full_path": (_guess_prefix(r.file_path) + r.path).replace("//", "/"),
            "handler": r.handler,
            "file_path": r.file_path,
            "line_number": r.line_number,
        }
        for r in scan_result.routes
    ]

    # 2. 查找匹配路由
    matched_route = None
    for route in scan_result.routes:
        if route.method.upper() == method:
            prefix = _guess_prefix(route.file_path)
            full_path = (prefix + route.path).replace("//", "/")
            # 尝试多种匹配方式
            if route.path == path or full_path == path:
                matched_route = route
                break
            # 部分路径匹配
            if path.endswith(route.path) or route.path.endswith(path.rstrip("/")):
                matched_route = route
                break

    if not matched_route:
        # 列出建议
        suggestions = [
            f"{r.method} {r.path}"
            for r in scan_result.routes
            if method in r.method.upper() or any(seg in r.path for seg in path.split("/") if seg)
        ][:10]
        return TraceResponse(
            ok=False,
            error=f"未找到匹配的路由: {method} {path}",
            all_routes=all_routes,
        )

    # 3. 追踪调用链
    tracer = CallChainTracer()
    call_result = tracer.trace_from_routes([matched_route], source_root)

    # 4. 提取表引用
    extractor = TableExtractor()
    extractor.scan_models(source_root)

    # 收集调用链中所有函数名
    all_func_names = set()
    for chain in call_result.chains:
        all_func_names.update(f for f in chain.chain if f != "...")

    # 在调用链函数中查找表引用
    table_usages = extractor.find_all_table_usages(list(all_func_names), source_root)

    # 也检查路由处理函数本身
    route_usages = extractor.find_tables_in_function(
        matched_route.handler,
        matched_route.file_path,
        source_root,
    )
    for u in route_usages:
        if u not in table_usages:
            table_usages.append(u)

    # 5. 构建泳道图
    diagram = build_swimlane(
        chains=call_result.chains,
        nodes=call_result.nodes,
        table_usages=table_usages,
        entry_point=f"{method} {path}",
    )

    # 6. 构建响应
    chain_nodes = []
    for chain in call_result.chains:
        for func_name in chain.chain:
            if func_name == "...":
                continue
            node = call_result.nodes.get(func_name, {})
            chain_nodes.append(NodeInfo(
                name=func_name,
                kind=node.get("kind", "function") if isinstance(node, dict) else "function",
                file_path=node.get("file_path", "") if isinstance(node, dict) else "",
                line_number=node.get("line_number", 0) if isinstance(node, dict) else 0,
            ))

    table_refs = [
        TableRef(
            table_name=tu.table_name,
            class_name=tu.class_name,
            operation=tu.operation,
            location=tu.location,
            file_path=tu.file_path,
            line_number=tu.line_number,
        )
        for tu in table_usages
    ]

    return TraceResponse(
        ok=True,
        entry_point=f"{matched_route.method} {matched_route.path}",
        route_info={
            "method": matched_route.method,
            "path": matched_route.path,
            "handler": matched_route.handler,
            "file_path": matched_route.file_path,
            "line_number": matched_route.line_number,
            "has_auth": matched_route.has_auth,
            "auth_deps": matched_route.auth_deps,
            "tags": matched_route.tags,
        },
        call_chain=chain_nodes,
        tables=table_refs,
        swimlane=diagram.mermaid_code,
        diagram_nodes=diagram.nodes,
        diagram_edges=diagram.edges,
        summary=diagram.summary,
        all_routes=all_routes,
    )
