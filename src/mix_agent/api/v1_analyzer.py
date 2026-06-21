"""接口调用链分析 API — 输入接口路径，分析代码调用过程、涉及的表，生成泳道图。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mix_agent.tools.parser.route_scanner import RouteScanner
from mix_agent.tools.parser.call_chain import CallChainTracer
from mix_agent.tools.parser.table_extractor import TableExtractor
from mix_agent.tools.parser.swimlane_builder import build_swimlane
from mix_agent.services.trace_store import trace_store

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
    code: str = ""  # 函数源码片段


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



# ── 路由：获取项目目录列表 ──


@router.get("/dirs")
def list_project_dirs(path: str = ".") -> dict:
    """列出指定路径下的子目录，供前端目录选择器使用。"""
    import os
    from pathlib import Path

    root = Path(path).resolve()
    if not root.exists():
        return {"ok": False, "error": f"路径不存在: {path}", "dirs": []}

    dirs = []
    try:
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith(".") and entry.name not in ("node_modules", "__pycache__", ".git", ".venv", "venv"):
                dirs.append({"name": entry.name, "path": str(entry.resolve()), "relative": str(entry)})
    except PermissionError:
        pass

    parents = []
    p = root.parent
    while len(parents) < 4:
        if p.is_dir() and str(p) != str(root):
            _name = p.name or str(p)  # 根目录 name 可能为空（如 "D:\\" → ""）
            parents.append({"name": _name, "path": str(p), "relative": str(p)})
        if p == p.parent:
            break
        p = p.parent

    return {"ok": True, "current": str(root), "dirs": dirs, "parents": parents}


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
            fp = node.get("file_path", "") if isinstance(node, dict) else ""
            if _is_external_path(fp):
                continue  # 过滤第三方库函数
            ln = node.get("line_number", 0) if isinstance(node, dict) else 0
            code = _read_function_code(func_name, fp, source_root) if fp else ""
            chain_nodes.append(NodeInfo(
                name=func_name,
                kind=node.get("kind", "function") if isinstance(node, dict) else "function",
                file_path=fp,
                line_number=ln,
                code=code,
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


# ── AI 增强调用链分析 ──


# 第三方/系统路径黑名单 — 这些路径中的函数不应出现在调用链分析中
_EXTERNAL_PATH_MARKERS = (
    ".venv", "venv", "site-packages", "__pycache__",
    "Lib/", "lib/python", "Python3", "Python",
    "google/protobuf", "idna/", "websockets/",
)


def _is_external_path(file_path: str) -> bool:
    """判断文件路径是否属于第三方库或系统路径，应被过滤。"""
    if not file_path:
        return False
    return any(marker in file_path.replace("\\", "/") for marker in _EXTERNAL_PATH_MARKERS)


def _sanitize_mermaid(code: str) -> str:
    """清理 AI 生成的 Mermaid 代码中的常见语法问题。"""
    import re

    # 0. 去掉 AI 可能包裹的 markdown 代码块标记
    code = re.sub(r'^```(?:mermaid)?\s*\n?', '', code, flags=re.IGNORECASE)
    code = re.sub(r'\n?```\s*$', '', code)

    # 1. 修复未加引号的方括号标签：将 [...内容...] 中没有双引号包裹的标签加上引号
    def _fix_node_label(m: re.Match) -> str:
        node_id = m.group(1)
        label = m.group(2)
        # 已经用引号包裹的跳过
        if label.startswith('"') and label.endswith('"'):
            return m.group(0)
        # 清理标签中的特殊字符
        clean = label.replace("/", " ").replace("(", " ").replace(")", " ").replace("{", " ").replace("}", " ").replace("<", " ").replace(">", " ")
        # 压缩多余空格
        clean = re.sub(r'\s+', ' ', clean).strip()
        return f'{node_id}["{clean}"]'

    code = re.sub(r'(\w+)\[([^\]]*?)\]', _fix_node_label, code)

    # 2. 修复子图标题中未加引号的部分
    #    subgraph frontend[🧑 前端 (Browser)] → subgraph frontend["🧑 前端 (Browser)"]
    def _fix_subgraph_label(m: re.Match) -> str:
        sub_id = m.group(1)
        label = m.group(2)
        if label.startswith('"') and label.endswith('"'):
            return m.group(0)
        return f'subgraph {sub_id}["{label}"]'

    code = re.sub(r'subgraph\s+(\w+)\[([^\]]+)\]', _fix_subgraph_label, code)

    # 3. 移除 HTML 标签
    code = re.sub(r'<br\s*/?\s*>', ', ', code, flags=re.IGNORECASE)

    # 4. 移除 HTML 实体
    code = code.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    # 5. 移除不可见控制字符（保留常用空白）
    code = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', code)

    # 6. 修复常见的错误箭头语法（如 -->> , ==> , —> 等）
    code = re.sub(r'-{3,}>', '-->', code)
    code = re.sub(r'=+>', '-->', code)

    # 7. 去掉空行过多（连续超过 2 个空行 → 1 个空行）
    code = re.sub(r'\n{3,}', '\n\n', code)

    return code.strip()


def _read_function_code(func_name: str, file_path: str, source_root: str = ".") -> str:
    """读取指定函数的源码片段。

    通过 AST 解析定位函数定义，提取完整函数体（最多 60 行）。
    """
    import ast
    from pathlib import Path

    if not file_path or not func_name:
        return ""

    full = Path(source_root) / file_path
    if not full.exists():
        full = Path(file_path)
    if not full.exists():
        return ""

    try:
        source = full.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    try:
        tree = ast.parse(source, filename=str(full))
    except SyntaxError:
        return ""

    lines = source.split("\n")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                start = node.lineno - 1  # 0-based
                end = getattr(node, "end_lineno", start + 1)
                # 限制最多 60 行
                snippet_lines = lines[start:min(end, start + 60)]
                return "\n".join(snippet_lines)

    return ""


class AiTraceRequest(BaseModel):
    """AI 增强调用链分析请求。"""
    method: str = Field(..., description="HTTP 方法 (GET/POST/PUT/DELETE/PATCH)")
    url: str = Field(..., description="完整请求 URL，如 http://localhost:8000/api/v1/proxy")
    headers: dict[str, str] = Field(default_factory=dict, description="请求头")
    body: str = Field(default="", description="请求体内容")
    source_root: str = Field(default=".", description="源码根目录")


class AiTraceResponse(BaseModel):
    """AI 增强调用链分析响应。"""
    ok: bool = True
    record_id: str = ""                     # 存储记录 ID，供前端删除/引用
    ai_swimlane: str = ""                    # AI 生成的三泳道图 (Mermaid)
    ai_summary: str = ""                     # AI 生成的自然语言分析
    call_chain: list[NodeInfo] = []          # 后端调用链
    tables: list[TableRef] = []              # 涉及的表
    swimlane: str = ""                       # 原始 AST 泳道图 (参考)
    diagram_nodes: list[dict] = []
    diagram_edges: list[dict] = []
    route_info: dict | None = None
    error: str = ""


@router.post("/ai-trace", response_model=AiTraceResponse)
async def ai_trace(body: AiTraceRequest) -> AiTraceResponse:
    """使用 AI 增强分析接口调用链，生成三泳道图（前端 → 后端 → 数据库/外部）。

    在 AST 静态分析的基础上，调用 LLM 补充：
    - 前端调用链（TypeScript fetch 链路）
    - 自然语言步骤解释
    - 三泳道 Mermaid 图（前端/后端/数据库）
    """
    from urllib.parse import urlparse
    from mix_agent.services.llm import llm_client
    from mix_agent.services.node_config import get_provider

    method = body.method.upper().strip()
    url = body.url.strip()
    source_root = body.source_root

    if not method or not url:
        return AiTraceResponse(ok=False, error="请提供 method 和 url 参数")

    # 1. 提取 path：尝试匹配本地路由
    parsed_url = urlparse(url)
    path = parsed_url.path or "/"

    # 2. 运行现有 AST 追踪（尝试 source_root 目录）
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

    # 查找匹配路由
    matched_route = None
    for route in scan_result.routes:
        if route.method.upper() == method:
            prefix = _guess_prefix(route.file_path)
            full_p = (prefix + route.path).replace("//", "/")
            if route.path == path or full_p == path:
                matched_route = route
                break
            if path.endswith(route.path) or route.path.endswith(path.rstrip("/")):
                matched_route = route
                break

    # 3. 追踪调用链 + 提取表
    chain_nodes: list[NodeInfo] = []
    table_refs: list[TableRef] = []
    ast_swimlane = ""
    ast_summary = ""
    diagram_nodes: list[dict] = []
    diagram_edges: list[dict] = []
    route_info = None

    if matched_route:
        tracer = CallChainTracer()
        call_result = tracer.trace_from_routes([matched_route], source_root)

        extractor = TableExtractor()
        extractor.scan_models(source_root)

        all_func_names: set[str] = set()
        for chain in call_result.chains:
            all_func_names.update(f for f in chain.chain if f != "...")
        table_usages = extractor.find_all_table_usages(list(all_func_names), source_root)
        route_usages = extractor.find_tables_in_function(
            matched_route.handler, matched_route.file_path, source_root
        )
        for u in route_usages:
            if u not in table_usages:
                table_usages.append(u)

        diagram = build_swimlane(
            chains=call_result.chains,
            nodes=call_result.nodes,
            table_usages=table_usages,
            entry_point=f"{method} {path}",
        )
        ast_swimlane = diagram.mermaid_code
        ast_summary = diagram.summary
        diagram_nodes = diagram.nodes
        diagram_edges = diagram.edges

        for chain in call_result.chains:
            for func_name in chain.chain:
                if func_name == "...":
                    continue
                node = call_result.nodes.get(func_name, {})
                fp = node.get("file_path", "") if isinstance(node, dict) else ""
                if _is_external_path(fp):
                    continue  # 过滤第三方库函数
                ln = node.get("line_number", 0) if isinstance(node, dict) else 0
                code = _read_function_code(func_name, fp, source_root) if fp else ""
                chain_nodes.append(NodeInfo(
                    name=func_name,
                    kind=node.get("kind", "function") if isinstance(node, dict) else "function",
                    file_path=fp,
                    line_number=ln,
                    code=code,
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

        route_info = {
            "method": matched_route.method,
            "path": matched_route.path,
            "handler": matched_route.handler,
            "file_path": matched_route.file_path,
            "line_number": matched_route.line_number,
        }

    # 4. 读取相关源文件，喂给 AI 做深度分析
    source_files: dict[str, str] = {}

    def _read_source(file_path: str, max_lines: int = 80) -> str:
        """读取源文件，截断过长的文件。"""
        if not file_path:
            return ""
        full = Path(source_root) / file_path
        if not full.exists():
            full = Path(file_path)
        if not full.exists():
            return ""
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            if len(lines) > max_lines:
                return "\n".join(lines[:max_lines]) + f"\n... (省略 {len(lines) - max_lines} 行)"
            return content
        except Exception:
            return ""

    # 读取匹配到的路由处理文件
    if route_info and route_info.get("file_path"):
        fpath = route_info["file_path"]
        code = _read_source(fpath, 80)
        if code:
            source_files[f"后端路由: {fpath}"] = code

    # 读取调用链中项目内部文件的源码（限制数量和长度）
    seen_files: set[str] = set()
    for cn in chain_nodes[:5]:  # 最多取前 5 个节点
        fp = cn.file_path
        if fp and fp.startswith("src") and fp not in seen_files and fp not in source_files:
            seen_files.add(fp)
            code = _read_source(fp, 40)
            if code:
                source_files[f"后端: {fp}"] = code

    # 读取前端 ApiClient 源码
    frontend_client = _read_source("frontend/src/api/client.ts", 60)
    if frontend_client:
        source_files["前端 API 层: frontend/src/api/client.ts"] = frontend_client
    frontend_page = _read_source("frontend/src/pages/ApiClient.tsx", 60)
    if frontend_page:
        # 只取核心发送逻辑部分
        lines = frontend_page.split("\n")
        send_start = 0
        for i, l in enumerate(lines):
            if "handleSend" in l or "sendProxyRequest" in l:
                send_start = max(0, i - 3)
                break
        excerpt = "\n".join(lines[send_start:send_start + 40])
        source_files["前端页面发送逻辑"] = excerpt

    # 5. 构建 LLM prompt：包含源码 + AST 结果
    source_code_block = ""
    for label, code in source_files.items():
        source_code_block += f"\n### {label}\n```\n{code}\n```\n"

    chain_desc = ""
    for cn in chain_nodes:
        chain_desc += f"  - {cn.kind}/{cn.name} @ {cn.file_path}:{cn.line_number}\n"
    if not chain_desc:
        chain_desc = "（未匹配到本地路由，该请求可能由代理直接转发到外部服务）"

    table_desc = "\n".join(
        f"  - {t.table_name} ({t.operation}) @ {t.location}" for t in table_refs
    ) or "（无）"

    headers_desc = "\n".join(f"  {k}: {v}" for k, v in body.headers.items()) if body.headers else "（无）"
    req_body_preview = body.body[:500] if body.body else "（无）"

    user_message = f"""请分析以下 API 请求的完整调用链路，生成三泳道 Mermaid 图。

【请求概览】
- 方法: {method}
- URL: {url}
- 请求头: {headers_desc}
- 请求体（截断 500 字符）: {req_body_preview}

【后端 AST 静态分析】
- 入口函数: {route_info.get('handler', '未知') if route_info else '未匹配本地路由'}
- 所在文件: {route_info.get('file_path', '—') if route_info else '—'}
- 调用链（仅项目内函数）:
{chain_desc}
- 涉及数据库表:
{table_desc}
- 分析摘要: {ast_summary or '（AST 追踪深度有限，请结合源码推断）'}

【关键源码参考（精简版）】
{source_code_block if source_code_block else "（未找到匹配的项目源码，请根据 URL 语义和常见 FastAPI 架构推断调用链路）"}

【输出要求】
1. 生成 Mermaid flowchart TD 三泳道图（frontend / backend / data）
2. 节点用中文描述，边用 --> 连接，形成 "前端→后端→数据层→后端→前端" 的完整闭环
3. 只输出 ===MERMAID=== / ===SUMMARY=== / ===END=== 三段，不要额外解释
4. SUMMARY 控制在 150 字以内"""


    # 5. 调用 LLM
    ai_swimlane = ast_swimlane  # fallback
    ai_summary_text = ast_summary  # fallback

    try:
        provider = get_provider("orchestrator")
        system_prompt = """你是一名资深的全栈架构师，擅长分析 API 调用链路并绘制泳道图。
你的任务是根据用户提供的 API 请求信息、源码片段和 AST 静态分析结果，
梳理完整的前端→后端→数据层调用过程，并生成标准的 Mermaid flowchart TD 三泳道图。

=== 核心原则 ===
1. **基于证据推断**：优先使用提供的源码和 AST 结果；当 AST 数据稀疏时，结合源码片段和 URL 语义合理推断，但不要凭空捏造不存在的步骤。
2. **简洁至上**：每个泳道保留 3-7 个关键节点，省略过于细节的步骤（如 "变量赋值"、"import 语句" 等）。
3. **中文描述**：所有节点标签使用中文，让非技术人员也能看懂。

=== Mermaid 语法规则（严格遵循）===
- 方向：flowchart TD（从上到下）
- 三个子图泳道：
  subgraph frontend["🧑 前端 (Browser)"]
  subgraph backend["⚙️ 后端 (FastAPI)"]
  subgraph data["🗄️ 数据层 / 外部服务"]
- 节点 ID：简短英文+数字，如 F1, F2, B1, B2, D1, D2
- 节点标签：用双引号包裹，如 F1["用户点击发送按钮"]
- 边：用 --> 连接，表达调用/数据流向
- **禁止**在标签中使用 / ( ) { } < > 等特殊字符（会破坏 Mermaid 语法），用中文描述替代
- **禁止**使用 <br/> 等 HTML 标签，用中文逗号或分号分隔
- **禁止**使用英文函数名作为节点标签（如 "proxy_request()"），改用中文描述（如 "路由处理：代理请求转发"）

=== 示例输出（参考格式）===
===MERMAID===
flowchart TD
    subgraph frontend["🧑 前端 (Browser)"]
        F1["用户在表单填写目标 URL 和方法"]
        F2["点击发送按钮触发 handleSend()"]
        F3["fetch() 发起 HTTP 请求到 /api/v1/proxy"]
        F4["接收响应并展示结果"]
    end
    subgraph backend["⚙️ 后端 (FastAPI)"]
        B1["CORS 中间件校验来源"]
        B2["AuthMiddleware 身份认证"]
        B3["路由处理器 proxy_request 接收请求"]
        B4["解析并校验 ProxyRequest 参数"]
        B5["构建目标 URL 并合并查询参数"]
        B6["httpx.AsyncClient 发起外部 HTTP 请求"]
        B7["封装 ProxyResponse 并返回"]
    end
    subgraph data["🗄️ 数据层 / 外部服务"]
        D1["目标外部 HTTP 服务"]
    end
    F2 --> F3
    F3 --> B1
    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> B5
    B5 --> B6
    B6 --> D1
    D1 --> B7
    B7 --> F4
===SUMMARY===
用户通过前端表单发起 HTTP 代理请求。请求经 CORS 校验和身份认证后，由 proxy_request 处理器解析参数、构建目标 URL，再通过 httpx 向外部服务转发。外部响应原样返回前端展示。该接口不涉及数据库操作。
===END===

=== 注意事项 ===
- 如果 AST 只找到路由 handler 一个节点，不要慌张：结合源码片段中的 imports、中间件配置、函数调用等推断完整链路。
- 如果请求头中包含 Authorization，说明前端会添加认证信息。
- 边的连接要形成完整闭环：前端发起 → 后端处理 → 数据层交互 → 后端响应 → 前端展示。
- SUMMARY 控制在 150 字以内。"""


        response = await asyncio.wait_for(
            llm_client.chat_with_prompt(
                provider=provider,
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.3,
                max_tokens=3072,
            ),
            timeout=60.0,
        )
        content = response.content.strip()

        # 解析 LLM 输出
        mermaid_start = content.find("===MERMAID===")
        mermaid_end = content.find("===SUMMARY===")
        summary_start = mermaid_end
        summary_end = content.find("===END===")

        if mermaid_start >= 0 and mermaid_end > mermaid_start:
            extracted_mermaid = content[mermaid_start + len("===MERMAID==="):mermaid_end].strip()
            if extracted_mermaid:
                ai_swimlane = _sanitize_mermaid(extracted_mermaid)

        if summary_start >= 0 and summary_end > summary_start:
            extracted_summary = content[summary_start + len("===SUMMARY==="):summary_end].strip()
            if extracted_summary:
                ai_summary_text = extracted_summary

    except asyncio.TimeoutError:
        ai_summary_text = f"AI 分析超时（60s），回退到 AST 静态分析结果:\n{ast_summary}"
    except Exception as e:
        ai_summary_text = f"AI 分析失败: {e}\n\n回退到 AST 静态分析结果:\n{ast_summary}"

    # 6. 持久化到 SQLite
    record_id = ""
    try:
        import hashlib
        record_id = hashlib.md5(f"{method}:{url}:{source_root}".encode()).hexdigest()[:24]
        trace_store.save(
            record_id=record_id,
            method=method,
            url=url,
            source_root=source_root,
            result={
                "ai_swimlane": ai_swimlane,
                "ai_summary": ai_summary_text,
                "call_chain": [n.model_dump() for n in chain_nodes],
                "tables": [t.model_dump() for t in table_refs],
                "swimlane": ast_swimlane,
                "diagram_nodes": diagram_nodes,
                "diagram_edges": diagram_edges,
                "route_info": route_info,
            },
        )
    except Exception:
        pass  # 存储失败不影响主流程

    return AiTraceResponse(
        ok=True,
        record_id=record_id,
        ai_swimlane=ai_swimlane,
        ai_summary=ai_summary_text,
        call_chain=chain_nodes,
        tables=table_refs,
        swimlane=ast_swimlane,
        diagram_nodes=diagram_nodes,
        diagram_edges=diagram_edges,
        route_info=route_info,
    )


# ── 分析历史 CRUD ──


class TraceHistoryItem(BaseModel):
    """历史记录摘要（不含完整 result 以减小响应体积）。"""
    id: str
    method: str
    url: str
    source_root: str | None = None
    created_at: str | None = None


class TraceHistoryListResponse(BaseModel):
    ok: bool = True
    items: list[TraceHistoryItem] = []
    total: int = 0


class TraceHistoryDetailResponse(BaseModel):
    ok: bool = True
    id: str = ""
    method: str = ""
    url: str = ""
    source_root: str | None = None
    result: dict | None = None
    created_at: str | None = None


@router.get("/trace-history", response_model=TraceHistoryListResponse)
def list_trace_history(limit: int = 20, offset: int = 0) -> TraceHistoryListResponse:
    """列出所有 AI 分析历史记录（按时间倒序）。"""
    items = trace_store.list_all(limit=limit, offset=offset)
    total = trace_store.count()
    return TraceHistoryListResponse(
        ok=True,
        items=[TraceHistoryItem(**item) for item in items],
        total=total,
    )


@router.get("/trace-history/{record_id}", response_model=TraceHistoryDetailResponse)
def get_trace_history(record_id: str) -> TraceHistoryDetailResponse:
    """获取单条历史记录的完整详情。"""
    item = trace_store.get(record_id)
    if item is None:
        return TraceHistoryDetailResponse(ok=False)
    return TraceHistoryDetailResponse(ok=True, **item)


@router.delete("/trace-history/{record_id}")
def delete_trace_history(record_id: str) -> dict:
    """删除单条历史记录。"""
    deleted = trace_store.delete(record_id)
    return {"ok": deleted}


@router.delete("/trace-history")
def clear_trace_history() -> dict:
    """清空全部历史记录。"""
    count = trace_store.delete_all()
    return {"ok": True, "deleted": count}
