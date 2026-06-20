"""代码审查 API — Git 历史、分支切换、文件查看、blame 分析。"""

from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import APIRouter, HTTPException, Query, Body

from mix_agent.tools.vcs.git_tool import GitTool, ChangedFile, CommitDetail
from mix_agent.services.llm import MODEL_REGISTRY

router = APIRouter()


def _git(repo_path: str = ".") -> GitTool:
    """获取 GitTool 实例。"""
    return GitTool(repo_path)


# ═══════════════════════════════════════════════════════════
# Commits
# ═══════════════════════════════════════════════════════════


@router.get("/commits")
def list_commits(
    branch: str = Query("HEAD", description="分支名或 commit ref"),
    max_count: int = Query(50, ge=1, le=500, description="最大返回条数"),
    skip: int = Query(0, ge=0, description="分页偏移"),
    file_path: str | None = Query(None, description="限定文件路径"),
    since: str | None = Query(None, description="起始日期 e.g. 2024-01-01"),
    until: str | None = Query(None, description="结束日期"),
    author: str | None = Query(None, description="作者过滤"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """获取提交历史列表。"""
    try:
        git = _git(repo_path)
        commits = git.log(
            branch=branch,
            max_count=max_count,
            skip=skip,
            file_path=file_path,
            since=since,
            until=until,
            author=author,
        )
        return {
            "ok": True,
            "branch": branch,
            "commits": [c.to_dict() for c in commits],
            "total": len(commits),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/commits/{sha}")
def get_commit_detail(
    sha: str,
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """获取单个 commit 详情（含变更文件列表和 diff）。"""
    try:
        git = _git(repo_path)
        detail = git.commit_detail(sha)
        return {
            "ok": True,
            "commit": detail.to_dict(),
            "raw_diff": detail.raw_diff,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Branches
# ═══════════════════════════════════════════════════════════


@router.get("/branches")
def list_branches(
    include_remote: bool = Query(False, description="是否包含远程分支"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """列出所有分支（含当前分支标记和最后提交信息）。"""
    try:
        git = _git(repo_path)
        branches = git.list_branches_detailed(include_remote=include_remote)
        current = git.current_branch()
        return {
            "ok": True,
            "current": current,
            "branches": [b.to_dict() for b in branches],
            "total": len(branches),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/branches/checkout")
def checkout_branch(
    branch: str = Query(..., description="目标分支名"),
    create: bool = Query(False, description="是否创建新分支 (git checkout -b)"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """切换分支。"""
    try:
        git = _git(repo_path)
        new_branch = git.checkout(branch, create=create)
        return {"ok": True, "current": new_branch, "checked_out": branch}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# File content
# ═══════════════════════════════════════════════════════════


@router.get("/file")
def read_file(
    file_path: str = Query(..., description="文件路径（相对于仓库根目录）"),
    revision: str = Query("HEAD", description="分支/commit/tag"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """读取指定 revision 下的文件内容。"""
    try:
        git = _git(repo_path)
        content = git.cat_file(file_path, revision=revision)
        return {
            "ok": True,
            "file_path": file_path,
            "revision": revision,
            "content": content,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Blame
# ═══════════════════════════════════════════════════════════


@router.get("/blame")
def blame_file(
    file_path: str = Query(..., description="文件路径"),
    revision: str = Query("HEAD", description="分支/commit"),
    line_start: int | None = Query(None, ge=1, description="起始行"),
    line_end: int | None = Query(None, ge=1, description="结束行"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """文件逐行归属分析（git blame）。"""
    try:
        git = _git(repo_path)
        lines = git.blame(file_path, revision=revision, line_start=line_start, line_end=line_end)
        return {
            "ok": True,
            "file_path": file_path,
            "revision": revision,
            "lines": [l.to_dict() for l in lines],
            "total": len(lines),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Diffs
# ═══════════════════════════════════════════════════════════


@router.get("/diffs")
def get_diff(
    target: str = Query("HEAD", description="目标分支/commit"),
    base: str = Query("main", description="基准分支"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """获取两个 ref 之间的差异。"""
    try:
        git = _git(repo_path)
        result = git.diff(target=target, base=base)
        return {
            "ok": True,
            "target": target,
            "base": base,
            **result.to_dict(),
            "raw_diff": result.raw_diff,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diffs/file")
def diff_file(
    file_path: str = Query(..., description="文件路径"),
    target: str = Query("HEAD", description="目标分支/commit"),
    base: str = Query("main", description="基准分支"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """获取单个文件的 diff。"""
    try:
        git = _git(repo_path)
        diff_text = git.diff_file(file_path, target=target, base=base)
        return {
            "ok": True,
            "file_path": file_path,
            "target": target,
            "base": base,
            "diff": diff_text,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Status
# ═══════════════════════════════════════════════════════════


@router.get("/status")
def repo_status(
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """获取工作区状态。"""
    try:
        git = _git(repo_path)
        status = git.status()
        return {"ok": True, **status.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Stashes
# ═══════════════════════════════════════════════════════════


@router.get("/stashes")
def list_stashes(
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """列出所有 stash。"""
    try:
        git = _git(repo_path)
        stashes = git.stash_list()
        return {
            "ok": True,
            "stashes": [s.to_dict() for s in stashes],
            "total": len(stashes),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stashes")
def create_stash(
    message: str = Query("", description="Stash 描述"),
    include_untracked: bool = Query(False, description="包含未跟踪文件"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """创建 stash。"""
    try:
        git = _git(repo_path)
        git.stash_push(message=message, include_untracked=include_untracked)
        return {"ok": True, "message": "Stash created"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stashes/pop")
def pop_stash(
    index: int = Query(0, ge=0, description="Stash 索引"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """弹出 stash。"""
    try:
        git = _git(repo_path)
        git.stash_pop(index=index)
        return {"ok": True, "message": f"Stash @{{{index}}} popped"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Tags & Remotes
# ═══════════════════════════════════════════════════════════


@router.get("/tags")
def list_tags(
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """列出所有 tag。"""
    try:
        git = _git(repo_path)
        tags = git.tag_list()
        return {
            "ok": True,
            "tags": [t.to_dict() for t in tags],
            "total": len(tags),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/remotes")
def list_remotes(
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """列出所有 remote。"""
    try:
        git = _git(repo_path)
        remotes = git.remote_list()
        return {
            "ok": True,
            "remotes": [r.to_dict() for r in remotes],
            "total": len(remotes),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Directory Browser
# ═══════════════════════════════════════════════════════════


@router.get("/dirs")
def list_dirs(
    path: str = Query(".", description="父目录路径"),
) -> dict:
    """列出指定路径下的子目录（含 .git 标记），用于目录选择器。"""
    from pathlib import Path
    import sys

    try:
        root = Path(path).resolve()
        if not root.exists():
            raise ValueError(f"Path does not exist: {root}")
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")

        entries: list[dict] = []
        try:
            for child in sorted(root.iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                is_git = (child / ".git").exists()
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "is_git_repo": is_git,
                })
        except PermissionError:
            pass  # 跳过无权限目录

        parent = str(root.parent) if str(root) != str(root.parent) else None

        # 系统根路径列表（切换盘符/根目录）
        roots: list[str] = []
        if sys.platform == "win32":
            import string
            from ctypes import windll
            drives = []
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & (1 << (ord(letter) - ord("A"))):
                    drives.append(f"{letter}:\\")
            roots = drives
        else:
            roots = ["/"]

        return {
            "ok": True,
            "path": str(root),
            "parent": parent,
            "entries": entries,
            "roots": roots,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# File Tree
# ═══════════════════════════════════════════════════════════


@router.get("/tree")
def file_tree(
    dir_path: str = Query("", description="子目录（空=仓库根）"),
    revision: str = Query("HEAD", description="分支/commit"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """列出仓库目录树（文件和子目录）。"""
    try:
        git = _git(repo_path)
        prefix = dir_path.strip("/") + "/" if dir_path.strip("/") else ""
        rev = f"{revision}:{prefix}" if prefix else f"{revision}:"
        output = git._run_git(["ls-tree", "--name-only", rev])

        entries: list[dict] = []
        for line in output.splitlines():
            name = line.strip()
            if not name:
                continue
            is_dir = name.endswith("/")
            clean_name = name.rstrip("/")
            full = f"{prefix}{clean_name}"
            entries.append({
                "name": clean_name,
                "path": full,
                "is_dir": is_dir,
            })

        return {
            "ok": True,
            "repo_path": str(git.repo_path),
            "revision": revision,
            "dir_path": dir_path,
            "entries": sorted(entries, key=lambda e: (not e["is_dir"], e["name"].lower())),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Code Search (grep)
# ═══════════════════════════════════════════════════════════


@router.get("/search")
def search_code(
    q: str = Query(..., description="搜索关键词"),
    repo_path: str = Query(".", description="仓库路径"),
    revision: str = Query("HEAD", description="分支/commit"),
    case_sensitive: bool = Query(False),
    max_results: int = Query(50, ge=1, le=200),
) -> dict:
    """在仓库中搜索代码（git grep）。"""
    try:
        git = _git(repo_path)
        args = ["grep", "--line-number", "-I"]
        if not case_sensitive:
            args.append("-i")
        args.extend(["-n", f"--max-count={max_results}"])
        args.extend([q, revision])
        output = git._run_git(args)

        results: list[dict] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                results.append({
                    "file": parts[0].strip(),
                    "line": int(parts[1]) if parts[1].strip().isdigit() else parts[1].strip(),
                    "content": parts[2].rstrip(),
                })

        return {
            "ok": True,
            "query": q,
            "revision": revision,
            "results": results[:max_results],
            "total": len(results),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# Open in VS Code
# ═══════════════════════════════════════════════════════════


@router.post("/open-in-vscode")
def open_in_vscode(
    file_path: str = Query(..., description="文件路径（相对于仓库）"),
    repo_path: str = Query(".", description="仓库路径"),
) -> dict:
    """在 VS Code 中打开指定文件。"""
    import subprocess
    import sys
    from pathlib import Path

    try:
        abs_path = Path(repo_path).resolve() / file_path
        if not abs_path.exists():
            raise ValueError(f"File does not exist: {abs_path}")

        # 尝试多种 known VS Code CLI 名称
        code_cmds = ["code", "code.cmd", "code-insiders"]
        launched = False
        errors: list[str] = []

        for cmd in code_cmds:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(
                        [cmd, "--reuse-window", str(abs_path)],
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.Popen(
                        [cmd, "--reuse-window", str(abs_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                launched = True
                break
            except FileNotFoundError:
                errors.append(f"{cmd} not found")
                continue

        if not launched:
            # Fallback: try opening via shell (for Windows where code.cmd might be in PATH)
            try:
                subprocess.Popen(
                    f'code --reuse-window "{abs_path}"',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                launched = True
            except Exception:
                errors.append("shell fallback failed")

        if not launched:
            raise RuntimeError(
                "无法打开 VS Code，请确保已安装 VS Code 并将其加入系统 PATH（code 命令可用）。"
                f" 尝试的命令: {', '.join(code_cmds)}"
            )

        return {"ok": True, "file_path": file_path, "abs_path": str(abs_path)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

import json as _json
import threading as _threading
from pathlib import Path as _Path

_CHECKLIST_PATH = _Path(__file__).resolve().parent.parent.parent.parent / "config" / "checklist_templates.json"
_checklist_lock = _threading.Lock()


# ═══════════════════════════════════════════════════════════
# AI Multi-Commit Review
# ═══════════════════════════════════════════════════════════

# ── In-memory store for async review jobs ──
_review_jobs: dict[str, dict] = {}
_review_jobs_lock = asyncio.Lock()

_REVIEW_JOB_TTL = 600  # auto-clean after 10 minutes


async def _run_review_background(job_id: str, commit_shas: list[str], repo_path: str):
    """后台执行 AI 审查，完成后写入 _review_jobs。"""
    from mix_agent.services.llm import llm_client

    try:
        git = _git(repo_path)

        commit_infos: list[dict] = []
        combined_diff_parts: list[str] = []
        all_changed_files: dict[str, ChangedFile] = {}
        total_additions = 0
        total_deletions = 0

        for sha in commit_shas:
            try:
                detail: CommitDetail = git.commit_detail(sha)
                commit_infos.append({
                    "sha": detail.sha,
                    "short_sha": detail.short_sha,
                    "author": detail.author,
                    "date": detail.date,
                    "message": detail.message,
                })
                header = f"--- Commit {detail.short_sha}: {detail.message.split(chr(10))[0][:80]} ---\n"
                combined_diff_parts.append(header + detail.raw_diff)
                total_additions += detail.total_additions
                total_deletions += detail.total_deletions
                for cf in detail.changed_files:
                    key = cf.file_path
                    if key not in all_changed_files:
                        all_changed_files[key] = cf
            except (ValueError, RuntimeError) as e:
                combined_diff_parts.append(f"--- Commit {sha[:8]}: failed to load ({e}) ---\n")

        if not combined_diff_parts:
            async with _review_jobs_lock:
                _review_jobs[job_id] = {"status": "failed", "error": "No diff content found for the selected commits"}
            return

        combined_diff = "\n\n".join(combined_diff_parts)
        changed_files_list = [cf.to_dict() for cf in all_changed_files.values()]

        user_message = f"""请审查以下 {len(commit_shas)} 个提交的代码变更。

## 提交列表
{chr(10).join(f"- [{c['short_sha']}] {c['message'][:100]}" for c in commit_infos)}

## 变更统计
- 修改文件数: {len(all_changed_files)}
- 新增行数: {total_additions}
- 删除行数: {total_deletions}

## 变更详情 (Diff)
```
{combined_diff[:80000]}
```
"""  # 截断 diff 防止超出 token 限制

        providers = list(MODEL_REGISTRY.keys())
        if not providers:
            async with _review_jobs_lock:
                _review_jobs[job_id] = {
                    "status": "failed",
                    "error": "No LLM provider configured. Please set up API keys in settings.",
                    "commit_infos": commit_infos,
                    "changed_files": changed_files_list,
                    "total_additions": total_additions,
                    "total_deletions": total_deletions,
                }
            return

        provider = providers[0]
        resp = await llm_client.chat(
            provider=provider,
            messages=[
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        async with _review_jobs_lock:
            _review_jobs[job_id] = {
                "status": "completed",
                "report": resp.content,
                "commit_infos": commit_infos,
                "changed_files": changed_files_list,
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "model": resp.model,
                "provider": resp.provider,
                "tokens": {
                    "prompt": resp.prompt_tokens,
                    "completion": resp.completion_tokens,
                    "total": resp.prompt_tokens + resp.completion_tokens,
                },
            }
    except Exception as e:
        async with _review_jobs_lock:
            _review_jobs[job_id] = {"status": "failed", "error": f"AI review failed: {e}"}


_REVIEW_SYSTEM_PROMPT = """你是一个资深的代码审查专家。请对以下多个提交的代码变更进行全面的代码审查。

请逐文件分析变更，关注以下方面：
1. **安全性**: SQL注入、XSS、权限绕过、敏感信息泄露等
2. **代码质量**: 可读性、可维护性、设计模式、命名规范
3. **性能**: N+1查询、内存泄漏、大循环、不必要的计算
4. **错误处理**: 异常捕获、错误日志、边界情况
5. **逻辑正确性**: 潜在bug、竞态条件、类型安全
6. **变更影响**: 对现有功能的影响，是否需要同步修改其他模块

输出格式要求（Markdown）：
```markdown
# 代码审查报告

## 概览
- 审查提交数：{count}
- 变更文件数：{files}
- 审查时间：{time}

## 高风险问题
### [高危/中危/低危] 问题标题
- **文件**: 文件路径 (行号)
- **说明**: 问题描述
- **建议**: 修复建议

## 改进建议
...

## 总结
总体评价和建议。
```"""


@router.post("/ai-review-commits")
async def ai_review_commits(body: dict) -> dict:
    """AI 评审多个提交的代码变更（异步）。

    接收 commit SHAs 列表，后台执行 LLM 审查，
    返回 task_id 供前端轮询。

    Request Body:
        commit_shas: list[str] — 要评审的 commit SHA 列表
        repo_path: str — 仓库路径（默认 ".")

    Returns:
        task_id: str — 异步任务 ID
        status: str — "processing"
    """
    commit_shas: list[str] = body.get("commit_shas", [])
    repo_path: str = body.get("repo_path", ".")

    if not commit_shas:
        raise HTTPException(status_code=400, detail="commit_shas is required")

    job_id = uuid.uuid4().hex[:12]
    async with _review_jobs_lock:
        _review_jobs[job_id] = {"status": "processing", "created_at": time.time()}

    asyncio.create_task(_run_review_background(job_id, commit_shas, repo_path))

    return {"task_id": job_id, "status": "processing"}


@router.get("/ai-review-result/{task_id}")
async def ai_review_result(task_id: str) -> dict:
    """查询 AI 审查异步任务的结果。

    Returns:
        status: "processing" | "completed" | "failed"
        report / error / commit_infos / ... — 完成时返回
    """
    async with _review_jobs_lock:
        job = _review_jobs.get(task_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if job["status"] == "processing":
        return {"ok": True, "status": "processing"}

    if job["status"] == "failed":
        # Clean expired jobs (best-effort)
        return {
            "ok": False,
            "status": "failed",
            "error": job.get("error", "Unknown error"),
            "commit_infos": job.get("commit_infos"),
            "changed_files": job.get("changed_files"),
            "total_additions": job.get("total_additions"),
            "total_deletions": job.get("total_deletions"),
        }

    # completed
    return {
        "ok": True,
        "status": "completed",
        "report": job.get("report"),
        "commit_infos": job.get("commit_infos"),
        "changed_files": job.get("changed_files"),
        "total_additions": job.get("total_additions"),
        "total_deletions": job.get("total_deletions"),
        "model": job.get("model"),
        "provider": job.get("provider"),
        "tokens": job.get("tokens"),
    }


def _load_checklists() -> dict:
    try:
        if _CHECKLIST_PATH.exists():
            return _json.loads(_CHECKLIST_PATH.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        pass
    return {"default": {"name": "默认清单", "items": [
        {"id": "security", "label": "安全检查", "hint": "SQL注入、XSS、权限绕过等"},
        {"id": "performance", "label": "性能检查", "hint": "N+1查询、内存泄漏、大循环等"},
        {"id": "style", "label": "代码风格", "hint": "命名、注释、格式一致性"},
        {"id": "error_handling", "label": "错误处理", "hint": "异常捕获、错误日志、fallback"},
        {"id": "testing", "label": "测试覆盖", "hint": "单元测试、集成测试是否充分"},
    ]}}


def _save_checklists(data: dict) -> None:
    _CHECKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _checklist_lock:
        _CHECKLIST_PATH.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@router.get("/checklists")
def list_checklists() -> dict:
    """列出所有审查清单模板。"""
    return {"ok": True, "checklists": _load_checklists()}


@router.put("/checklists")
def save_checklist(body: dict) -> dict:
    """保存审查清单模板。

    Example: PUT /review/checklists
    {"name": "安全审查", "items": [{"id":"xss","label":"XSS检查"},...]}
    """
    name = body.get("name", "").strip()
    items = body.get("items", [])
    if not name or not isinstance(items, list):
        return {"ok": False, "error": "name and items[] are required."}
    data = _load_checklists()
    data[name] = {"name": name, "items": items}
    _save_checklists(data)
    return {"ok": True, "name": name, "items": len(items)}
