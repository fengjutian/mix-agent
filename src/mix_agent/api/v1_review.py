"""代码审查 API — Git 历史、分支切换、文件查看、blame 分析。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from mix_agent.tools.vcs.git_tool import GitTool

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
