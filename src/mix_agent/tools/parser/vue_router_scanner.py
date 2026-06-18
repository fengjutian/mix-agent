"""Vue Router 扫描器 — 扫描 Vue/React Router 前端路由定义和导航守卫。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FrontendRoute:
    """单条前端路由。"""
    path: str
    component: str = ""
    file_path: str = ""
    line_number: int = 0
    has_guard: bool = False     # beforeEach / beforeEnter
    guard_type: str = ""         # "auth" | "role" | "none"
    meta: dict = field(default_factory=dict)


@dataclass
class FrontendRouteResult:
    """前端路由扫描结果。"""
    routes: list[FrontendRoute] = field(default_factory=list)
    guards: list[dict] = field(default_factory=list)
    framework: str = ""          # "vue" | "react" | "unknown"


class VueRouterScanner:
    """Vue Router / React Router 前端路由扫描器。

    支持：
    - Vue Router: createRouter({ routes: [...] }), beforeEach
    - React Router: <Route path="..." element={...} />
    - 导航守卫: beforeEach, beforeEnter, meta.requiresAuth
    """

    def __init__(self):
        pass

    # ── 公开 API ──

    def scan_file(self, file_path: str | Path) -> FrontendRouteResult:
        """扫描单个文件。"""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in (".js", ".ts"):
            return self._scan_js_ts(path)
        elif ext in (".jsx", ".tsx"):
            return self._scan_jsx_tsx(path)
        elif ext == ".vue":
            return self._scan_vue(path)

        return FrontendRouteResult()

    def scan_directory(self, root: str | Path = ".") -> FrontendRouteResult:
        """扫描目录下所有前端路由文件。"""
        root_path = Path(root)
        merged = FrontendRouteResult(framework="vue")

        # 常见路由文件位置
        patterns = [
            "**/router/**/*.{js,ts,jsx,tsx}",
            "**/routes/**/*.{js,ts,jsx,tsx}",
            "**/pages/**/*.{vue,jsx,tsx}",
        ]

        seen = set()
        for pattern in patterns:
            for fp in root_path.glob(pattern):
                if str(fp) in seen:
                    continue
                seen.add(str(fp))
                result = self.scan_file(fp)
                merged.routes.extend(result.routes)
                merged.guards.extend(result.guards)
                if result.framework:
                    merged.framework = result.framework

        return merged

    # ── 内部扫描 ──

    def _scan_js_ts(self, path: Path) -> FrontendRouteResult:
        """扫描 JS/TS 路由文件（Vue Router createRouter 格式）。"""
        result = FrontendRouteResult(framework="vue")
        content = path.read_text(encoding="utf-8", errors="replace")

        # 匹配 createRouter routes 数组中的路径
        # path: '/xxx', component: ..., meta: { requiresAuth: true }
        route_pattern = re.compile(
            r"\{\s*path\s*:\s*['\"]([^'\"]+)['\"](.*?)\}",
            re.DOTALL,
        )
        for match in route_pattern.finditer(content):
            path_val = match.group(1)
            block = match.group(2)

            component = ""
            comp_match = re.search(r"component\s*:\s*(\w+)", block)
            if comp_match:
                component = comp_match.group(1)

            has_guard = "requiresAuth" in block or "beforeEnter" in block
            guard_type = "auth" if "requiresAuth" in block else "none"

            meta: dict = {}
            if "requiresAuth" in block:
                meta["requiresAuth"] = True
            if "roles" in block:
                roles_match = re.search(r"roles\s*:\s*\[([^\]]+)\]", block)
                if roles_match:
                    meta["roles"] = [r.strip().strip("'\"") for r in roles_match.group(1).split(",")]

            line_no = content[:match.start()].count("\n") + 1
            result.routes.append(FrontendRoute(
                path=path_val,
                component=component,
                file_path=str(path),
                line_number=line_no,
                has_guard=has_guard,
                guard_type=guard_type,
                meta=meta,
            ))

        # 匹配 beforeEach 守卫
        if "beforeEach" in content:
            result.guards.append({
                "type": "beforeEach",
                "file": str(path),
                "description": "全局前置守卫",
            })

        return result

    def _scan_jsx_tsx(self, path: Path) -> FrontendRouteResult:
        """扫描 JSX/TSX 路由文件（React Router <Route> 格式）。"""
        result = FrontendRouteResult(framework="react")
        content = path.read_text(encoding="utf-8", errors="replace")

        # 匹配 <Route path="/xxx" element={<Component />} />
        route_pattern = re.compile(
            r'<Route\s+path\s*=\s*["\']([^"\']+)["\'](.*?)(?:/>|>)',
            re.DOTALL,
        )
        for match in route_pattern.finditer(content):
            path_val = match.group(1)
            block = match.group(2)

            component = ""
            comp_match = re.search(r'element\s*=\s*\{<(\w+)', block)
            if comp_match:
                component = comp_match.group(1)

            line_no = content[:match.start()].count("\n") + 1
            result.routes.append(FrontendRoute(
                path=path_val,
                component=component,
                file_path=str(path),
                line_number=line_no,
                has_guard=False,
            ))

        return result

    def _scan_vue(self, path: Path) -> FrontendRouteResult:
        """扫描 .vue 单文件组件。"""
        result = FrontendRouteResult(framework="vue")
        content = path.read_text(encoding="utf-8", errors="replace")

        # 检查是否有 <route-meta> 或 export default 中的路由信息
        if "beforeRouteEnter" in content or "beforeRouteUpdate" in content:
            result.guards.append({
                "type": "component_guard",
                "file": str(path),
                "description": "组件内导航守卫",
            })

        return result
