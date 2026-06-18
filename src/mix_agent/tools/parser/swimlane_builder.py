"""泳道图生成器 — 将调用链 + 表引用组装为 Mermaid swimlane 图表。"""

from __future__ import annotations

from dataclasses import dataclass, field

from mix_agent.tools.parser.call_chain import CallChain, CallNode
from mix_agent.tools.parser.table_extractor import TableUsage


@dataclass
class SwimlaneDiagram:
    """泳道图结果。"""
    mermaid_code: str                                    # Mermaid 图表代码
    lanes: list[str] = field(default_factory=list)       # 泳道名称列表
    nodes: list[dict] = field(default_factory=list)      # 节点详情
    edges: list[dict] = field(default_factory=list)       # 边详情
    summary: str = ""                                     # 文字摘要


# 中文标签映射
LANE_LABELS = {
    "client": "🧑 Client",
    "route": "🚏 Route 层",
    "service": "⚙️ Service 层",
    "dao": "📦 DAO 层",
    "db": "🗄️ Database",
    "function": "📁 通用函数",
}


def classify_lane(node_kind: str) -> str:
    """将节点类型映射到泳道。"""
    kind = node_kind.lower() if node_kind else "function"
    if kind in ("route", "controller"):
        return "route"
    if kind in ("service", "manager"):
        return "service"
    if kind in ("dao", "repository", "repo"):
        return "dao"
    if kind in ("db", "model", "database"):
        return "db"
    return "function"


def build_swimlane(
    chains: list[CallChain],
    nodes: dict[str, CallNode],
    table_usages: list[TableUsage],
    entry_point: str = "",
) -> SwimlaneDiagram:
    """从调用链和表引用构建泳道图。

    Args:
        chains: 调用链列表
        nodes: 节点字典（func_name → CallNode）
        table_usages: 该接口涉及的表使用列表
        entry_point: 入口点描述（如 "POST /api/v1/tasks/"）

    Returns:
        SwimlaneDiagram: 含 Mermaid 代码和结构化数据
    """
    # 收集所有涉及的节点（按泳道分组）
    lanes: dict[str, list[str]] = {
        "client": [],
        "route": [],
        "service": [],
        "dao": [],
        "db": [],
    }

    # 添加客户端节点
    entry_label = entry_point or (chains[0].entry_point if chains else "API Request")
    lanes["client"].append(f'CLIENT["{entry_label}"]')

    node_set: set[str] = set()
    edge_set: set[tuple[str, str]] = set()

    # 从调用链提取节点和边
    for chain in chains:
        for i, func_name in enumerate(chain.chain):
            if func_name == "...":
                continue
            node_set.add(func_name)

            # 分类到泳道
            node_info = nodes.get(func_name, {})
            kind = node_info.get("kind", "function") if isinstance(node_info, dict) else "function"
            lane = classify_lane(kind)
            if lane not in lanes:
                lane = "function"
                if lane not in lanes:
                    lanes[lane] = []

            # 节点定义（取简短名称避免重复）
            node_id = _sanitize_id(func_name)
            lanes[lane].append(f'{node_id}["{func_name}"]')

            # 边：从前一个节点连接过来
            if i > 0:
                prev = chain.chain[i - 1]
                if prev != "...":
                    edge_set.add((_sanitize_id(prev), node_id))

        # 如果有表引用，连接到相关的表节点
        if table_usages:
            last_func = next(
                (f for f in reversed(chain.chain) if f != "..."), None
            )
            if last_func:
                last_id = _sanitize_id(last_func)
                for tu in table_usages:
                    tbl_id = f'TBL_{_sanitize_id(tu.table_name)}'
                    if tbl_id not in str(lanes.get("db", [])):
                        lanes["db"].append(f'{tbl_id}["📋 {tu.table_name}\n({tu.operation})"]')
                    edge_set.add((last_id, tbl_id))

    # 如果没有从调用链发现表，但 table_usages 非空，添加孤立表节点
    if not any(tbl_id for tbl_id in lanes.get("db", [])):
        for tu in table_usages:
            tbl_id = f'TBL_{_sanitize_id(tu.table_name)}'
            lanes["db"].append(f'{tbl_id}["📋 {tu.table_name}\n({tu.operation})"]')

    # 连接 CallChain 中第一个节点到 Client
    if chains and chains[0].chain and chains[0].chain[0] != "...":
        first_func = chains[0].chain[0]
        first_id = _sanitize_id(first_func)
        edge_set.add(("CLIENT", first_id))

    # 构建 Mermaid 代码
    mermaid_lines = ["flowchart LR"]

    # 各泳道
    for lane_key in ("client", "route", "service", "dao", "db"):
        node_defs = lanes.get(lane_key, [])
        if node_defs or lane_key in ("client",):  # client 泳道始终显示
            label = LANE_LABELS.get(lane_key, lane_key)
            mermaid_lines.append(f"    subgraph {lane_key}[{label}]")
            mermaid_lines.append(f"        direction LR")
            for nd in (node_defs or []):
                mermaid_lines.append(f"        {nd}")
            mermaid_lines.append("    end")

    # 边
    for src, dst in sorted(edge_set):
        mermaid_lines.append(f"    {src} --> {dst}")

    mermaid_code = "\n".join(mermaid_lines)

    # 结构化节点和边
    node_list = []
    for func_name in node_set:
        n = nodes.get(func_name, {})
        node_list.append({
            "id": _sanitize_id(func_name),
            "name": func_name,
            "kind": n.get("kind", "function") if isinstance(n, dict) else "function",
            "file_path": n.get("file_path", "") if isinstance(n, dict) else "",
            "line_number": n.get("line_number", 0) if isinstance(n, dict) else 0,
        })

    edge_list = [{"from": s, "to": d} for s, d in sorted(edge_set)]

    # 摘要
    all_tables = sorted(set(tu.table_name for tu in table_usages))
    summary_parts = [f"入口: {entry_point or (chains[0].entry_point if chains else '未知')}"]
    if all_tables:
        summary_parts.append(f"涉及表: {', '.join(all_tables)}")
    summary_parts.append(f"调用深度: {max((c.depth for c in chains), default=0)}")
    summary_parts.append(f"触达数据库: {'是' if any(c.reaches_db for c in chains) else '否'}")

    return SwimlaneDiagram(
        mermaid_code=mermaid_code,
        lanes=list(lanes.keys()),
        nodes=node_list,
        edges=edge_list,
        summary=" | ".join(summary_parts),
    )


def _sanitize_id(name: str) -> str:
    """将函数名/表名转换为合法的 Mermaid 节点 ID。"""
    return name.replace(".", "_").replace("/", "_").replace("-", "_").replace(" ", "_")
