"""mix-agent CLI — Phase 1 确定性扫描命令行入口。

用法：
    mix-agent scan --repo . --target HEAD --base main
    mix-agent serve  # 启动 FastAPI 服务
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mix_agent.services.task_service import TaskService


def cmd_scan(args: argparse.Namespace) -> int:
    """执行确定性扫描并输出报告。"""
    service = TaskService()

    print(f"Scanning {args.repo}: {args.base}...{args.target}")
    task = service.create_task(
        description=args.description or f"Scan {args.base}..{args.target}",
        target_branch=args.target,
        base_branch=args.base,
        repo_path=args.repo,
    )

    print(f"\nTask: {task.task_id}")
    print(f"Status: {task.status.value}")

    if task.status.value == "failed":
        print("Scan failed", file=sys.stderr)
        return 1

    findings = service.get_findings(task.task_id)
    report = service.get_report(task.task_id, fmt=args.format)

    if findings is None or report is None:
        print("No results", file=sys.stderr)
        return 1

    # 输出
    if args.format == "json":
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False, default=str))
    elif args.format == "md":
        _print_md_report(report)
    else:
        # 默认简洁输出
        print(f"\nChanged files: {len(report.changed_files)}")
        for cf in report.changed_files:
            print(f"  {cf.get('change_type', '?'):8s} {cf['file_path']}")

        print(f"\nFindings ({report.total_findings}): "
              f"{report.danger_count} danger, {report.warning_count} warning")

        for f in findings.findings:
            icon = "!!" if f.risk_level == "danger" else "! " if f.risk_level == "warning" else "  "
            loc = f"{f.file_path}:{f.line_number}" if f.file_path else "-"
            print(f"  {icon} [{f.agent}] {f.finding_type}: {f.description[:80]} ({loc})")

    return 0


def _print_md_report(report) -> None:
    """输出 Markdown 格式报告。"""
    print(f"# Mix-Agent Audit Report")
    print(f"\n**Task ID:** {report.task_id}")
    print(f"\n## Summary\n\n{report.summary}")
    print(f"\n**Total Findings:** {report.total_findings} "
          f"({report.danger_count} danger, {report.warning_count} warning)")
    print(f"\n## Changed Files\n")
    for cf in report.changed_files:
        print(f"- `{cf['file_path']}` ({cf.get('change_type', '?')}, +{cf.get('additions', 0)}/-{cf.get('deletions', 0)})")
    print(f"\n## Findings\n")
    for f in report.findings:
        risk = f.risk_level.upper()
        print(f"- **[{risk}]** `{f.agent}/{f.finding_type}`: {f.description}")


def cmd_serve(args: argparse.Namespace) -> int:
    """启动 FastAPI 服务。"""
    import uvicorn
    from mix_agent.config import settings

    uvicorn.run(
        "mix_agent.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="mix-agent",
        description="Enterprise multi-agent code security audit system",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    # scan
    p_scan = sub.add_parser("scan", help="Run deterministic security scan")
    p_scan.add_argument("--repo", default=".", help="Repository path")
    p_scan.add_argument("--target", default="HEAD", help="Target branch/commit")
    p_scan.add_argument("--base", default="main", help="Base branch")
    p_scan.add_argument("--description", default="", help="Task description")
    p_scan.add_argument("--format", default="text", choices=["text", "json", "md"], help="Output format")
    p_scan.set_defaults(func=cmd_scan)

    # serve
    p_serve = sub.add_parser("serve", help="Start FastAPI server")
    p_serve.add_argument("--host", default="0.0.0.0", help="Bind host")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
