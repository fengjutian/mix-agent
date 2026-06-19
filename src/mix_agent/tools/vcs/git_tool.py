"""Git 差异分析工具 — 通过 git CLI 获取两个分支间的文件变更列表、提交历史、文件内容等。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class FileStatus(str, Enum):
    """工作区文件状态。"""
    UNTRACKED = "untracked"
    MODIFIED = "modified"
    STAGED = "staged"
    DELETED = "deleted"
    RENAMED = "renamed"
    CLEAN = "clean"


@dataclass
class ChangedFile:
    """单个变更文件信息。"""
    file_path: str
    change_type: ChangeType
    old_path: str | None = None  # renamed 场景下的旧路径
    additions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "change_type": self.change_type.value,
            "old_path": self.old_path,
            "additions": self.additions,
            "deletions": self.deletions,
        }


@dataclass
class DiffResult:
    """Git Diff 执行结果。"""
    changed_files: list[ChangedFile] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    raw_diff: str = ""

    def to_dict(self) -> dict:
        return {
            "changed_files": [f.to_dict() for f in self.changed_files],
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
        }


@dataclass
class CommitInfo:
    """单条提交记录。"""
    sha: str
    short_sha: str
    author: str
    author_email: str
    date: str          # ISO 8601
    message: str
    refs: list[str] = field(default_factory=list)  # branches / tags 指向该 commit

    def to_dict(self) -> dict:
        return {
            "sha": self.sha,
            "short_sha": self.short_sha,
            "author": self.author,
            "author_email": self.author_email,
            "date": self.date,
            "message": self.message,
            "refs": self.refs,
        }


@dataclass
class CommitDetail(CommitInfo):
    """包含变更文件列表的提交详情。"""
    changed_files: list[ChangedFile] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    raw_diff: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "changed_files": [f.to_dict() for f in self.changed_files],
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
        })
        return base


@dataclass
class BlameLine:
    """单行 blame 信息。"""
    line_number: int
    content: str
    commit_sha: str
    short_sha: str
    author: str
    date: str
    summary: str  # commit message 摘要

    def to_dict(self) -> dict:
        return {
            "line_number": self.line_number,
            "content": self.content,
            "commit_sha": self.commit_sha,
            "short_sha": self.short_sha,
            "author": self.author,
            "date": self.date,
            "summary": self.summary,
        }


@dataclass
class StatusResult:
    """工作区状态。"""
    branch: str
    status_items: list[dict] = field(default_factory=list)  # [{file_path, status, staged}]
    is_clean: bool = True

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "status_items": self.status_items,
            "is_clean": self.is_clean,
        }


@dataclass
class StashInfo:
    """单条 stash 信息。"""
    index: int
    message: str
    branch: str
    date: str

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "message": self.message,
            "branch": self.branch,
            "date": self.date,
        }


@dataclass
class TagInfo:
    """单条 tag 信息。"""
    name: str
    sha: str
    short_sha: str
    message: str = ""
    date: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sha": self.sha,
            "short_sha": self.short_sha,
            "message": self.message,
            "date": self.date,
        }


@dataclass
class RemoteInfo:
    """单个 remote 信息。"""
    name: str
    url: str
    type: str = ""  # fetch / push

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "type": self.type,
        }


@dataclass
class BranchInfo:
    """单个分支信息。"""
    name: str
    is_current: bool = False
    is_remote: bool = False
    last_commit_sha: str = ""
    last_commit_short: str = ""
    last_commit_date: str = ""
    last_commit_message: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_current": self.is_current,
            "is_remote": self.is_remote,
            "last_commit_sha": self.last_commit_sha,
            "last_commit_short": self.last_commit_short,
            "last_commit_date": self.last_commit_date,
            "last_commit_message": self.last_commit_message,
        }


class GitTool:
    """基于本地 Git CLI 的全功能工具。

    提供差异分析、提交历史、分支管理、文件查看、blame 等功能。
    前提：用户本地已安装 Git。
    """

    def __init__(self, repo_path: str | Path = ".", timeout: int = 30):
        self.repo_path = Path(repo_path).resolve()
        self.timeout = timeout

    # ═══════════════════════════════════════════════════════════
    # Diff
    # ═══════════════════════════════════════════════════════════

    def diff(self, target: str = "HEAD", base: str = "main") -> DiffResult:
        """获取 base...target 之间变更文件列表及统计。

        Args:
            target: 目标分支/commit（默认 HEAD）
            base: 基准分支（默认 main）

        Returns:
            DiffResult: 包含 changed_files、total_additions、total_deletions、raw_diff
        """
        self._ensure_repo()

        diff_range = f"{base}...{target}"

        name_status = self._run_git(["diff", "--name-status", diff_range])
        numstat = self._run_git(["diff", "--numstat", diff_range])
        raw_diff = self._run_git(["diff", diff_range])

        return self._parse_diff(name_status, numstat, raw_diff)

    def diff_file(self, file_path: str, target: str = "HEAD", base: str = "main") -> str:
        """获取单个文件的 diff 内容。"""
        self._ensure_repo()
        diff_range = f"{base}...{target}"
        return self._run_git(["diff", diff_range, "--", file_path])

    # ═══════════════════════════════════════════════════════════
    # Log / Commit history
    # ═══════════════════════════════════════════════════════════

    def log(
        self,
        branch: str = "HEAD",
        max_count: int = 50,
        skip: int = 0,
        file_path: str | None = None,
        since: str | None = None,   # e.g. "2024-01-01"
        until: str | None = None,
        author: str | None = None,
    ) -> list[CommitInfo]:
        """获取提交历史。

        Args:
            branch: 分支名或 commit ref
            max_count: 最大返回条数
            skip: 跳过前 N 条（分页）
            file_path: 可选，限定某个文件的提交历史
            since: 起始日期过滤
            until: 结束日期过滤
            author: 作者过滤

        Returns:
            list[CommitInfo]
        """
        self._ensure_repo()

        args = ["log", "--format=%H|%h|%an|%ae|%aI|%D|%s",
                f"-{max_count}", f"--skip={skip}"]
        if file_path:
            args.append("--")
            args.append(file_path)
        if since:
            args.append(f"--since={since}")
        if until:
            args.append(f"--until={until}")
        if author:
            args.append(f"--author={author}")
        args.append(branch)

        output = self._run_git(args)
        return self._parse_log(output)

    def commit_detail(self, sha: str) -> CommitDetail:
        """获取单个 commit 的详细信息（含变更文件列表和 diff）。

        Args:
            sha: commit SHA

        Returns:
            CommitDetail: 含 changed_files 和 raw_diff
        """
        self._ensure_repo()

        # 获取基本信息
        info_output = self._run_git([
            "log", "--format=%H|%h|%an|%ae|%aI|%s|%D",
            "-1", sha,
        ])
        commits = self._parse_log(info_output)
        if not commits:
            raise ValueError(f"Commit not found: {sha}")
        commit = commits[0]

        # 获取变更文件
        name_status = self._run_git(["diff", "--name-status", f"{sha}~1..{sha}"])
        numstat = self._run_git(["diff", "--numstat", f"{sha}~1..{sha}"])
        raw_diff = self._run_git(["diff", f"{sha}~1..{sha}"])

        diff_result = self._parse_diff(name_status, numstat, raw_diff)

        return CommitDetail(
            sha=commit.sha,
            short_sha=commit.short_sha,
            author=commit.author,
            author_email=commit.author_email,
            date=commit.date,
            message=commit.message,
            refs=commit.refs,
            changed_files=diff_result.changed_files,
            total_additions=diff_result.total_additions,
            total_deletions=diff_result.total_deletions,
            raw_diff=diff_result.raw_diff,
        )

    # ═══════════════════════════════════════════════════════════
    # Branches
    # ═══════════════════════════════════════════════════════════

    def list_branches(self) -> list[str]:
        """列出所有本地分支名。"""
        self._ensure_repo()
        output = self._run_git(["branch", "--format=%(refname:short)"])
        return [line.strip() for line in output.splitlines() if line.strip()]

    def list_branches_detailed(self, include_remote: bool = False) -> list[BranchInfo]:
        """列出所有分支（含详细信息和最后提交）。

        Args:
            include_remote: 是否包含远程分支

        Returns:
            list[BranchInfo]
        """
        self._ensure_repo()

        format_str = "%(refname:short)|%(objectname)|%(objectname:short)|%(committerdate:iso)|%(subject)"
        args = ["branch", f"--format={format_str}"]
        if include_remote:
            args.append("-a")
        output = self._run_git(args)

        current = self.current_branch()
        branches: list[BranchInfo] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            # 用 | 分割，但 message 可能含 |，所以只取前 4 个字段，其余归入 message
            parts = line.split("|")
            if len(parts) < 5:
                continue
            name = parts[0].strip()
            is_remote = name.startswith("remotes/")
            if is_remote:
                # 保留 origin/ 前缀以避免与本地分支重名
                name = name.replace("remotes/", "")
            branches.append(BranchInfo(
                name=name,
                is_current=(name == current),
                is_remote=is_remote,
                last_commit_sha=parts[1].strip(),
                last_commit_short=parts[2].strip(),
                last_commit_date=parts[3].strip(),
                last_commit_message="|".join(p.strip() for p in parts[4:]),
            ))

        return branches

    def current_branch(self) -> str:
        """获取当前分支名。"""
        self._ensure_repo()
        return self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def checkout(self, branch: str, create: bool = False) -> str:
        """切换分支。

        Args:
            branch: 目标分支名
            create: 是否创建新分支（相当于 git checkout -b）

        Returns:
            str: 当前分支名
        """
        self._ensure_repo()

        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(branch)

        output = self._run_git(args)
        return self.current_branch()

    # ═══════════════════════════════════════════════════════════
    # File content / Show
    # ═══════════════════════════════════════════════════════════

    def cat_file(self, file_path: str, revision: str = "HEAD") -> str:
        """读取指定 revision 下的文件内容。

        Args:
            file_path: 文件路径（相对于仓库根目录）
            revision: 分支/commit/tag（默认 HEAD）

        Returns:
            str: 文件内容
        """
        self._ensure_repo()
        return self._run_git(["show", f"{revision}:{file_path}"])

    def show(self, revision: str) -> str:
        """显示某个 revision 的完整信息（commit message + diff）。

        Args:
            revision: commit SHA / branch / tag

        Returns:
            str: git show 输出
        """
        self._ensure_repo()
        return self._run_git(["show", revision])

    def rev_parse(self, revision: str) -> str:
        """解析 revision 为完整 SHA。

        Args:
            revision: 分支/commit/tag/HEAD 等

        Returns:
            str: 完整 commit SHA
        """
        self._ensure_repo()
        return self._run_git(["rev-parse", revision]).strip()

    # ═══════════════════════════════════════════════════════════
    # Blame
    # ═══════════════════════════════════════════════════════════

    def blame(self, file_path: str, revision: str = "HEAD",
              line_start: int | None = None, line_end: int | None = None) -> list[BlameLine]:
        """文件逐行归属分析。

        Args:
            file_path: 文件路径
            revision: 分支/commit
            line_start: 起始行号（1-based），None 表示全文
            line_end: 结束行号（1-based），None 表示全文

        Returns:
            list[BlameLine]
        """
        self._ensure_repo()

        args = ["blame", "--date=iso", "--line-porcelain"]
        if line_start is not None and line_end is not None:
            args.extend(["-L", f"{line_start},{line_end}"])
        args.extend([revision, "--", file_path])

        output = self._run_git(args)
        return self._parse_blame(output)

    # ═══════════════════════════════════════════════════════════
    # Stash
    # ═══════════════════════════════════════════════════════════

    def stash_list(self) -> list[StashInfo]:
        """列出所有 stash。"""
        self._ensure_repo()
        output = self._run_git(["stash", "list", "--format=%gd|%gs|%aI"])
        stashes: list[StashInfo] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            # parts[0] e.g. "stash@{0}"
            index_str = parts[0].strip()
            try:
                idx = int(index_str.replace("stash@{", "").replace("}", ""))
            except ValueError:
                idx = len(stashes)
            stashes.append(StashInfo(
                index=idx,
                message=parts[1].strip(),
                branch="",
                date=parts[2].strip(),
            ))
        return stashes

    def stash_push(self, message: str = "", include_untracked: bool = False) -> None:
        """创建 stash。

        Args:
            message: stash 描述
            include_untracked: 是否包含未跟踪文件
        """
        self._ensure_repo()
        args = ["stash", "push"]
        if include_untracked:
            args.append("--include-untracked")
        if message:
            args.extend(["-m", message])
        self._run_git(args)

    def stash_pop(self, index: int = 0) -> None:
        """弹出 stash。

        Args:
            index: stash 索引（默认 0）
        """
        self._ensure_repo()
        self._run_git(["stash", "pop", f"stash@{{{index}}}"])

    # ═══════════════════════════════════════════════════════════
    # Tags
    # ═══════════════════════════════════════════════════════════

    def tag_list(self) -> list[TagInfo]:
        """列出所有 tag。"""
        self._ensure_repo()
        format_str = "%(refname:short)|%(objectname)|%(objectname:short)|%(subject)|%(creatordate:iso)"
        output = self._run_git(["tag", f"--format={format_str}", "--sort=-creatordate"])
        tags: list[TagInfo] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 5:
                continue
            tags.append(TagInfo(
                name=parts[0].strip(),
                sha=parts[1].strip(),
                short_sha=parts[2].strip(),
                message=parts[3].strip(),
                date=parts[4].strip(),
            ))
        return tags

    # ═══════════════════════════════════════════════════════════
    # Remotes
    # ═══════════════════════════════════════════════════════════

    def remote_list(self) -> list[RemoteInfo]:
        """列出所有 remote。"""
        self._ensure_repo()
        output = self._run_git(["remote", "-v"])
        remotes: dict[str, RemoteInfo] = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            name = parts[0]
            url = parts[1]
            rtype = parts[2].strip("()")
            if name not in remotes:
                remotes[name] = RemoteInfo(name=name, url=url, type=rtype)
        return list(remotes.values())

    # ═══════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════

    def status(self) -> StatusResult:
        """获取工作区状态。

        Returns:
            StatusResult: 分支名 + 变更文件列表
        """
        self._ensure_repo()
        branch = self.current_branch()
        output = self._run_git(["status", "--porcelain"])

        items: list[dict] = []
        is_clean = True
        for line in output.splitlines():
            if not line.strip():
                continue
            is_clean = False
            index_status = line[0]    # staged
            worktree_status = line[1] # unstaged
            file_path = line[3:].strip()

            status_code = worktree_status if worktree_status != " " else index_status
            status_map = {
                "?": FileStatus.UNTRACKED,
                "M": FileStatus.MODIFIED,
                "A": FileStatus.STAGED,
                "D": FileStatus.DELETED,
                "R": FileStatus.RENAMED,
            }
            status = status_map.get(status_code, FileStatus.MODIFIED)

            items.append({
                "file_path": file_path,
                "status": status.value,
                "staged": index_status != " ",
            })

        return StatusResult(branch=branch, status_items=items, is_clean=is_clean)

    # ═══════════════════════════════════════════════════════════
    # 内部实现
    # ═══════════════════════════════════════════════════════════

    def _ensure_repo(self) -> None:
        """验证路径是有效的 Git 仓库。"""
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git(self, args: list[str]) -> str:
        """执行 git 命令并返回 stdout。"""
        cmd = ["git", "-C", str(self.repo_path)] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                if "unknown revision" in stderr or "not a git repository" in stderr:
                    raise ValueError(f"Git error: {stderr}")
                return ""
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def _parse_diff(self, name_status: str, numstat: str, raw_diff: str) -> DiffResult:
        """解析 git diff 输出为 DiffResult。"""
        result = DiffResult(raw_diff=raw_diff)

        stat_map: dict[str, tuple[int, int]] = {}
        for line in numstat.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                add = int(parts[0]) if parts[0] != "-" else 0
                delete = int(parts[1]) if parts[1] != "-" else 0
                file_path = parts[2].strip()
                stat_map[file_path] = (add, delete)

        for line in name_status.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status_char = parts[0][0]
            rest = "\t".join(parts[1:])

            if status_char == "R":
                rename_parts = rest.split("\t")
                if len(rename_parts) >= 2:
                    old_path = rename_parts[0]
                    new_path = rename_parts[1]
                else:
                    old_path = rest
                    new_path = rest
                change_type = ChangeType.RENAMED
                file_path = new_path
                old = old_path
            else:
                file_path = rest
                old = None
                if status_char == "A":
                    change_type = ChangeType.ADDED
                elif status_char == "D":
                    change_type = ChangeType.DELETED
                elif status_char == "M":
                    change_type = ChangeType.MODIFIED
                else:
                    change_type = ChangeType.MODIFIED

            add, delete = stat_map.get(file_path, (0, 0))
            result.total_additions += add
            result.total_deletions += delete

            result.changed_files.append(ChangedFile(
                file_path=file_path,
                change_type=change_type,
                old_path=old,
                additions=add,
                deletions=delete,
            ))

        return result

    def _parse_log(self, output: str) -> list[CommitInfo]:
        """解析 git log 输出。"""
        commits: list[CommitInfo] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            # 格式: %H|%h|%an|%ae|%aI|%D|%s — %s 在末尾避免 | 干扰
            parts = line.split("|")
            if len(parts) < 6:
                continue
            refs_str = parts[5].strip() if len(parts) > 5 else ""
            refs = [r.strip() for r in refs_str.split(",") if r.strip()]
            message = "|".join(p.strip() for p in parts[6:]) if len(parts) > 6 else ""
            commits.append(CommitInfo(
                sha=parts[0].strip(),
                short_sha=parts[1].strip(),
                author=parts[2].strip(),
                author_email=parts[3].strip(),
                date=parts[4].strip(),
                message=message,
                refs=refs,
            ))
        return commits

    def _parse_blame(self, output: str) -> list[BlameLine]:
        """解析 git blame --line-porcelain 输出。"""
        lines: list[BlameLine] = []
        current_commit = ""
        current_short = ""
        current_author = ""
        current_date = ""
        current_summary = ""
        current_line_no = 0

        for raw_line in output.splitlines():
            if raw_line.startswith("\t"):
                # 实际内容行
                content = raw_line[1:]
                current_line_no += 1
                lines.append(BlameLine(
                    line_number=current_line_no,
                    content=content,
                    commit_sha=current_commit,
                    short_sha=current_short,
                    author=current_author,
                    date=current_date,
                    summary=current_summary,
                ))
                continue

            if " " not in raw_line:
                continue
            key, value = raw_line.split(" ", 1)
            if key == "author":
                current_author = value
            elif key == "author-time":
                current_date = value
            elif key == "summary":
                current_summary = value
            elif len(key) == 40:  # commit hash
                current_commit = key
                current_short = key[:8]

        return lines
