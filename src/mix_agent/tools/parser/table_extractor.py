"""表提取器 — 扫描 ORM 模型定义并检测代码中对表的引用。

从 models.py 提取 SQLAlchemy 表映射，然后在指定函数/文件的 AST 中
检测对 ORM 模型类或原生表名的引用。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TableInfo:
    """数据库表信息。"""
    class_name: str           # ORM 模型类名，如 User
    table_name: str           # 物理表名，如 users
    file_path: str            # 定义所在文件
    line_number: int          # 类定义行号
    columns: list[str] = field(default_factory=list)  # 列名列表
    relationships: list[str] = field(default_factory=list)  # 关联的其他表


@dataclass
class TableUsage:
    """表在一次函数调用中的使用信息。"""
    table_name: str           # 物理表名
    class_name: str | None    # ORM 类名
    operation: str            # SELECT / INSERT / UPDATE / DELETE / UNKNOWN
    location: str             # 所在函数名
    file_path: str
    line_number: int


class TableExtractor:
    """数据库表提取器。

    1. 扫描 models.py 或全部 .py 文件，提取 SQLAlchemy Base 子类及其 __tablename__。
    2. 提供方法在给定 AST/函数中检测表引用。
    """

    # 常见数据库操作方法名
    DB_METHODS = {
        "query", "execute", "add", "delete", "merge", "flush",
        "commit", "rollback", "bulk_insert_mappings", "bulk_save_objects",
        "select", "insert", "update",  # SQLAlchemy Core
        "text",  # raw SQL
    }

    # SQL 关键字 → 操作类型
    SQL_OPERATIONS = {
        "select": "SELECT",
        "insert": "INSERT",
        "update": "UPDATE",
        "delete": "DELETE",
        "create": "DDL",
        "alter": "DDL",
        "drop": "DDL",
    }

    def __init__(self):
        self._tables: dict[str, TableInfo] = {}          # class_name → TableInfo
        self._table_by_tablename: dict[str, TableInfo] = {}  # table_name → TableInfo

    # ── 公开 API ──

    def scan_models(self, source_root: str | Path = ".") -> dict[str, TableInfo]:
        """扫描源目录下所有 .py 文件，提取 ORM 模型定义。

        Returns:
            dict: class_name → TableInfo
        """
        root = Path(source_root)
        self._tables.clear()
        self._table_by_tablename.clear()

        for py_file in root.rglob("*.py"):
            if self._should_skip(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
                self._scan_file(tree, str(py_file))
            except (SyntaxError, OSError):
                pass

        return self._tables

    def find_tables_in_function(
        self, func_name: str, file_path: str, source_root: str | Path = "."
    ) -> list[TableUsage]:
        """在指定函数的 AST 中检测对数据库表的引用。

        Args:
            func_name: 函数名
            file_path: 函数所在文件
            source_root: 源码根目录

        Returns:
            list[TableUsage]: 该函数中检测到的表引用
        """
        root = Path(source_root)
        path = root / file_path if not Path(file_path).is_absolute() else Path(file_path)

        if not path.exists():
            return []

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, OSError):
            return []

        usages: list[TableUsage] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name:
                    usages.extend(self._scan_function_body(node, str(path)))
                    break

        return usages

    def find_all_table_usages(
        self, func_names: list[str], source_root: str | Path = "."
    ) -> list[TableUsage]:
        """批量查找多个函数中的表引用。

        Args:
            func_names: 函数名列表
            source_root: 源码根目录

        Returns:
            list[TableUsage]: 去重后的表引用列表
        """
        root = Path(source_root)
        # 定位每个函数所在文件和函数体
        all_usages: list[TableUsage] = []
        seen: set[tuple[str, str, str]] = set()  # (table_name, operation, location) 去重

        for py_file in root.rglob("*.py"):
            if self._should_skip(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name in func_names:
                            usages = self._scan_function_body(node, str(py_file))
                            for u in usages:
                                key = (u.table_name, u.operation, u.location)
                                if key not in seen:
                                    seen.add(key)
                                    all_usages.append(u)
            except (SyntaxError, OSError):
                pass

        return all_usages

    def get_table_info(self, name: str) -> TableInfo | None:
        """通过类名或物理表名查找表信息。"""
        return self._tables.get(name) or self._table_by_tablename.get(name)

    @property
    def all_tables(self) -> list[TableInfo]:
        return list(self._tables.values())

    # ── 内部实现 ──

    def _should_skip(self, path: Path) -> bool:
        parts = path.parts
        skip = {"__pycache__", "node_modules", ".git", ".venv", "venv", "dist", "build", ".tox"}
        return any(s in parts for s in skip) or path.suffix != ".py"

    def _scan_file(self, tree: ast.Module, file_path: str) -> None:
        """扫描单个文件，提取 ORM 模型定义。"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                table_info = self._extract_model_class(node, file_path)
                if table_info:
                    self._tables[table_info.class_name] = table_info
                    self._table_by_tablename[table_info.table_name] = table_info

    def _extract_model_class(
        self, node: ast.ClassDef, file_path: str
    ) -> TableInfo | None:
        """判断类是否是 SQLAlchemy 模型，提取信息。"""
        # 检查是否继承 Base / DeclarativeBase
        has_base = False
        for base in node.bases:
            base_name = self._name_of(base)
            if base_name in ("Base", "DeclarativeBase"):
                has_base = True
                break

        if not has_base:
            return None

        table_name = ""
        columns: list[str] = []
        relationships: list[str] = []

        for item in node.body:
            # 提取 __tablename__
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        if isinstance(item.value, ast.Constant):
                            table_name = item.value.value
                        elif isinstance(item.value, ast.Str):  # Python <3.8
                            table_name = item.value.s
            # 提取列定义
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name):
                    col_name = item.target.name
                    if not col_name.startswith("_") and col_name not in ("id",):
                        columns.append(col_name)
                # 检查是否有 relationship 调用
                if item.value and isinstance(item.value, ast.Call):
                    if self._name_of(item.value.func) == "relationship":
                        if isinstance(item.target, ast.Name):
                            relationships.append(item.target.name)

        if not table_name:
            return None

        return TableInfo(
            class_name=node.name,
            table_name=table_name,
            file_path=file_path,
            line_number=node.lineno,
            columns=columns,
            relationships=relationships,
        )

    def _scan_function_body(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str
    ) -> list[TableUsage]:
        """扫描函数体，检测对 ORM 模型类或表名的引用。"""
        usages: list[TableUsage] = []
        func_name = func_node.name

        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                usage = self._detect_table_in_call(node, func_name, file_path)
                if usage:
                    usages.append(usage)

            # 检测字符串常量中的 SQL
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                sql_usages = self._detect_sql_table(node.value, func_name, file_path, node.lineno)
                usages.extend(sql_usages)

        return usages

    def _detect_table_in_call(
        self, call: ast.Call, func_name: str, file_path: str
    ) -> TableUsage | None:
        """检测函数调用中是否引用了 ORM 模型类。"""
        # 检测 select(User), session.query(User), session.execute(select(User)) 等
        for arg in call.args:
            class_name = self._name_of(arg)
            if class_name and class_name in self._tables:
                return TableUsage(
                    table_name=self._tables[class_name].table_name,
                    class_name=class_name,
                    operation=self._infer_operation(call),
                    location=func_name,
                    file_path=file_path,
                    line_number=call.lineno,
                )

        # 也检测 func 本身（如 session.query(User)）
        func = call.func
        if isinstance(func, ast.Attribute):
            for kw in call.keywords:
                pass  # 暂无需要处理的关键字参数
            # 检查所有 args
            for arg in call.args:
                class_name = self._name_of(arg)
                if class_name and class_name in self._tables:
                    return TableUsage(
                        table_name=self._tables[class_name].table_name,
                        class_name=class_name,
                        operation=self._infer_operation(call),
                        location=func_name,
                        file_path=file_path,
                        line_number=call.lineno,
                    )

        return None

    def _detect_sql_table(
        self, sql: str, func_name: str, file_path: str, lineno: int
    ) -> list[TableUsage]:
        """检测原生 SQL 字符串中的表名引用。"""
        usages: list[TableUsage] = []
        sql_lower = sql.lower().strip()

        # 提取 SQL 操作类型
        operation = "UNKNOWN"
        for keyword, op in self.SQL_OPERATIONS.items():
            if sql_lower.startswith(keyword):
                operation = op
                break

        # 检测已知表名
        for table_name, info in self._table_by_tablename.items():
            if table_name.lower() in sql_lower:
                usages.append(TableUsage(
                    table_name=table_name,
                    class_name=info.class_name,
                    operation=operation,
                    location=func_name,
                    file_path=file_path,
                    line_number=lineno,
                ))

        return usages

    def _infer_operation(self, call: ast.Call) -> str:
        """根据调用上下文推断数据库操作类型。"""
        func_name = self._name_of(call.func).lower()
        if any(w in func_name for w in ("insert", "add", "create", "save")):
            return "INSERT"
        if any(w in func_name for w in ("update", "modify", "change", "set")):
            return "UPDATE"
        if any(w in func_name for w in ("delete", "remove", "drop", "purge")):
            return "DELETE"
        if any(w in func_name for w in ("select", "query", "get", "find", "fetch", "list", "search")):
            return "SELECT"
        return "UNKNOWN"

    @staticmethod
    def _name_of(node: ast.AST | None) -> str:
        """从 AST 节点提取名称。"""
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return TableExtractor._name_of(node.func)
        return ""
