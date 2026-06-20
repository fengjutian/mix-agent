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


def _sanitize_mermaid(code: str) -> str:
    """清理 AI 生成的 Mermaid 代码中的常见语法问题。"""
    import re

    # 1. 修复未加引号的方括号标签：将 [...内容...] 中没有双引号包裹的标签加上引号
    #    但要保留已经有引号的，以及子图标题（subgraph X["label"]）
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

    # 2. 移除 HTML 标签
    code = re.sub(r'<br\s*/?\s*>', ', ', code, flags=re.IGNORECASE)

    # 3. 移除 HTML 实体
    code = code.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    # 4. 确保节点 ID 不含特殊字符
    #    (已经通过 re.sub 处理，这里是额外保障)

    return code


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
        code = _read_source(fpath, 120)
        if code:
            source_files[f"后端路由: {fpath}"] = code

    # 读取调用链中项目内部文件的源码
    seen_files: set[str] = set()
    for cn in chain_nodes:
        fp = cn.file_path
        if fp and fp.startswith("src") and fp not in seen_files and fp not in source_files:
            seen_files.add(fp)
            code = _read_source(fp, 60)
            if code:
                source_files[f"后端: {fp}"] = code

    # 读取前端 ApiClient 源码
    frontend_client = _read_source("frontend/src/api/client.ts", 80)
    if frontend_client:
        source_files["前端 API 层: frontend/src/api/client.ts"] = frontend_client
    frontend_page = _read_source("frontend/src/pages/ApiClient.tsx", 100)
    if frontend_page:
        # 只取核心发送逻辑部分
        lines = frontend_page.split("\n")
        # 找 handleSend 函数
        send_start = 0
        for i, l in enumerate(lines):
            if "handleSend" in l or "sendProxyRequest" in l:
                send_start = max(0, i - 5)
                break
        excerpt = "\n".join(lines[send_start:send_start + 60])
        source_files["前端页面: frontend/src/pages/ApiClient.tsx (发送逻辑)"] = excerpt

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

    user_message = f"""请分析以下 API 请求的完整调用过程，并生成一个三泳道 Mermaid flowchart TD（从上到下）图表。

【请求信息】
- 方法: {method}
- URL: {url}
- 请求头: {headers_desc}
- 请求体（截断）: {req_body_preview}

【项目源码参考】
{source_code_block if source_code_block else "（未找到项目源码，请根据 URL 语义推断）"}

【后端 AST 静态分析结果】
- 入口: {route_info.get('handler', '未知') if route_info else '未匹配本地路由'}
- 文件: {route_info.get('file_path', '未知') if route_info else '—'}
- 调用链:
{chain_desc}
- 涉及数据库表:
{table_desc}
- 摘要: {ast_summary or '—'}

【要求】
1. 你从这个请求的 URL 和方法推断：前端是如何发起调用的（使用 fetch API，从 ApiClient 页面的"发送"按钮触发）
2. 后端经过哪些层（CORS 中间件 → AuthMiddleware → 路由 handler → Service → 外部 HTTP / 数据库）
3. 生成一个 Mermaid flowchart TD 三泳道图，分为三个子图:
   - subgraph frontend["🧑 前端 (Browser)"]
   - subgraph backend["⚙️ 后端 (FastAPI - mix-agent)"]
   - subgraph data["🗄️ 数据层 / 外部服务"]
4. 每个泳道内的节点用中文描述（如 "用户点击发送按钮"、"fetch() 发起请求"、"CORS 中间件校验"）
5. 节点间用 --> 连接
6. 只输出 Mermaid 代码和一个中文分析总结，格式如下：

===MERMAID===
flowchart TD
    subgraph frontend[...]
        ...
    end
    ...
===SUMMARY===
（150 字以内的中文分析总结）
===END==="""

    # 5. 调用 LLM
    ai_swimlane = ast_swimlane  # fallback
    ai_summary_text = ast_summary  # fallback

    try:
        provider = get_provider("orchestrator")
        system_prompt = """你是一名资深的全栈架构师，擅长分析 API 调用链路并绘制泳道图。
你的任务是根据用户提供的 API 请求信息和 AST 静态分析结果，
梳理完整的前端→后端→数据层调用过程，并生成标准的 Mermaid flowchart TD 三泳道图。

规则：
- 泳道图方向为 TD（从上到下）
- 三个泳道：frontend / backend / data
- 节点 ID 使用简短英文（如 F1, B2, D3），节点标签用双引号包裹
- 示例写法：F1["用户点击发送按钮"]
- 禁止在节点标签中使用 /, (, ), {, }, <, > 等特殊字符，用中文替代
- 禁止使用 HTML 标签（如 <br/>），用中文逗号分隔
- 保持简洁，每个泳道 3-7 个节点
- 输出格式严格遵循 ===MERMAID=== / ===SUMMARY=== / ===END==="""

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

    return AiTraceResponse(
        ok=True,
        ai_swimlane=ai_swimlane,
        ai_summary=ai_summary_text,
        call_chain=chain_nodes,
        tables=table_refs,
        swimlane=ast_swimlane,
        diagram_nodes=diagram_nodes,
        diagram_edges=diagram_edges,
        route_info=route_info,
    )
