"""基于 Python 标准库 `ast` 的代码符号表提取与业务摘要生成器。

Phase 1 使用 Python ast 标准库，免去 Tree-sitter 的 C 绑定和跨平台编译依赖。
Tree-sitter 多语言支持移入 Phase 2。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


class ASTAnalyzer:
    """Python AST 静态代码分析器。

    从 Python 源码文件中提取类/函数符号表、导入关系、调用关系，
    并生成自然语言业务摘要。
    """

    def __init__(self):
        pass

    # ── 公开接口 ──

    def parse_file(self, file_path: str | Path) -> dict[str, Any]:
        """解析单个 Python 源码文件，返回符号表。"""
        file_path = Path(file_path)
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        classes = self._extract_classes(tree)
        functions = self._extract_functions(tree)
        imports = self._extract_imports(tree)
        calls = self._extract_calls(tree)

        return {
            "file": str(file_path),
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "calls": calls,
        }

    def parse_files(self, file_paths: list[str | Path]) -> dict[str, Any]:
        """批量解析多个文件，返回聚合符号表。"""
        all_symbols: dict[str, Any] = {}
        errors: list[dict] = []

        for fp in file_paths:
            try:
                all_symbols[str(fp)] = self.parse_file(fp)
            except (SyntaxError, OSError) as e:
                errors.append({"file": str(fp), "error": str(e)})

        return {
            "files": all_symbols,
            "errors": errors,
            "total_files": len(file_paths),
            "parsed_files": len(all_symbols),
        }

    # ── 公开辅助方法 ──

    def extract_classes(self, source: str) -> list[dict[str, Any]]:
        """提取类定义及其方法签名。"""
        tree = ast.parse(source)
        return self._extract_classes(tree)

    def extract_functions(self, source: str) -> list[dict[str, Any]]:
        """提取函数定义及其签名。"""
        tree = ast.parse(source)
        return self._extract_functions(tree)

    def generate_summary(self, source: str) -> str:
        """基于符号表生成自然语言业务摘要。"""
        tree = ast.parse(source)
        classes = self._extract_classes(tree)
        functions = self._extract_functions(tree)
        imports = self._extract_imports(tree)

        parts: list[str] = []

        # 模块级 docstring
        doc = ast.get_docstring(tree)
        if doc:
            parts.append(f"模块描述: {doc.strip().split(chr(10))[0]}")

        # 导入的模块
        if imports:
            module_names = sorted({i["module"] for i in imports if i.get("module")})
            if module_names:
                parts.append(f"依赖模块: {', '.join(module_names[:10])}")

        # 类
        if classes:
            class_names = [c["name"] for c in classes]
            parts.append(f"定义类 ({len(classes)}): {', '.join(class_names)}")

        # 函数
        if functions:
            func_names = [f["name"] for f in functions]
            parts.append(f"定义函数 ({len(functions)}): {', '.join(func_names)}")

        return "。".join(parts) + "。" if parts else "（无有效符号）"

    # ── 内部实现 ──

    def _extract_classes(self, tree: ast.Module) -> list[dict[str, Any]]:
        """从 AST 提取所有类定义。"""
        classes: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods: list[dict[str, Any]] = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(self._function_info(item))
                classes.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "bases": [self._name_of(b) for b in node.bases],
                    "decorators": [self._name_of(d) for d in node.decorator_list],
                    "methods": methods,
                })
        return classes

    def _extract_functions(self, tree: ast.Module) -> list[dict[str, Any]]:
        """从 AST 提取所有模块级函数定义。"""
        functions: list[dict[str, Any]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._function_info(node))
        return functions

    def _function_info(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
        """提取单个函数的元信息。"""
        args_info: list[dict[str, Any]] = []
        for arg in node.args.args:
            ann = self._name_of(arg.annotation) if arg.annotation else None
            args_info.append({"name": arg.arg, "annotation": ann})

        returns = self._name_of(node.returns) if node.returns else None
        decorators = [self._name_of(d) for d in node.decorator_list]

        return {
            "name": node.name,
            "lineno": node.lineno,
            "args": args_info,
            "returns": returns,
            "decorators": decorators,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        }

    def _extract_imports(self, tree: ast.Module) -> list[dict[str, Any]]:
        """从 AST 提取所有导入语句。"""
        imports: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"type": "import", "module": alias.name, "alias": alias.asname})
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append({
                        "type": "importfrom",
                        "module": node.module,
                        "name": alias.name,
                        "alias": alias.asname,
                    })
        return imports

    def _extract_calls(self, tree: ast.Module) -> list[dict[str, Any]]:
        """从 AST 提取所有函数调用。"""
        calls: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_info = {
                    "name": self._name_of(node.func),
                    "lineno": node.lineno,
                }
                calls.append(call_info)
        return calls

    def _name_of(self, node: ast.AST | None) -> str | None:
        """将 AST 节点转为可读名称字符串。"""
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._name_of(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            return f"{self._name_of(node.value)}[...]"
        if isinstance(node, ast.Call):
            return f"{self._name_of(node.func)}(...)"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        return type(node).__name__

    # ── JSON 序列化 ──

    def to_json(self, file_paths: list[str | Path]) -> str:
        """解析并输出 JSON 格式符号表。"""
        result = self.parse_files(file_paths)
        return json.dumps(result, ensure_ascii=False, indent=2)
