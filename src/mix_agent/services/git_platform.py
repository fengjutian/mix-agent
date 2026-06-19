"""Git 平台集成 — GitHub / GitLab API 客户端。

功能：
- 解析仓库 URL，自动识别平台
- 列出 Pull Request / Merge Request
- 获取 PR 详情（源/目标分支、标题、描述）
- 获取 PR diff & 变更文件列表
- 使用 API Token 认证（从 config/git_tokens.json 读取）
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

# ── Token 存储 ──

TOKENS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "config" / "git_tokens.json"


def _ensure_file() -> None:
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TOKENS_FILE.exists():
        TOKENS_FILE.write_text(json.dumps({}, indent=2), encoding="utf-8")


def get_token(platform: str) -> str:
    """获取指定平台的 API Token。"""
    _ensure_file()
    try:
        data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return ""
    return data.get(platform, {}).get("token", "")


def set_token(platform: str, token: str) -> None:
    """设置平台 API Token。"""
    _ensure_file()
    try:
        data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        data = {}
    data[platform] = {"token": token}
    TOKENS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── 数据模型 ──


@dataclass
class PRInfo:
    """Pull Request / Merge Request 信息。"""
    number: int
    title: str
    description: str = ""
    state: str = "open"          # open / closed / merged
    source_branch: str = ""
    target_branch: str = ""
    author: str = ""
    url: str = ""
    created_at: str = ""
    updated_at: str = ""
    platform: str = "github"     # github / gitlab

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "title": self.title,
            "description": self.description,
            "state": self.state,
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "author": self.author,
            "url": self.url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "platform": self.platform,
        }


@dataclass
class PRDetail(PRInfo):
    """PR 详情（含 diff 和变更文件）。"""
    changed_files: list[dict] = field(default_factory=list)
    raw_diff: str = ""
    total_additions: int = 0
    total_deletions: int = 0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "changed_files": self.changed_files,
            "raw_diff": self.raw_diff,
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
        })
        return base


# ── 仓库 URL 解析 ──


@dataclass
class RepoRef:
    """解析后的仓库引用。"""
    platform: str      # github / gitlab
    owner: str
    repo: str
    base_url: str      # e.g. https://api.github.com


def parse_repo_url(url: str) -> RepoRef | None:
    """解析 GitHub / GitLab 仓库 URL。

    Supports:
        https://github.com/owner/repo
        https://gitlab.com/owner/repo
        https://github.com/owner/repo.git
        git@github.com:owner/repo.git
    """
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # SSH 格式: git@github.com:owner/repo
    m = re.match(r"git@([^:]+):(.+)/(.+)$", url)
    if m:
        host, owner, repo = m.groups()
        platform = "gitlab" if "gitlab" in host else "github"
        base = f"https://api.github.com" if platform == "github" else f"https://{host}/api/v4"
        return RepoRef(platform=platform, owner=owner, repo=repo, base_url=base)

    # HTTPS 格式
    parsed = urlparse(url)
    host = parsed.hostname or ""
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        return None

    if "github.com" in host:
        platform = "github"
        base = "https://api.github.com"
    elif "gitlab" in host:
        platform = "gitlab"
        base = f"{parsed.scheme}://{host}/api/v4"
    else:
        return None

    return RepoRef(
        platform=platform,
        owner=parts[-2],
        repo=parts[-1],
        base_url=base,
    )


# ── HTTP 客户端 ──


class GitPlatformClient:
    """GitHub / GitLab API 客户端（同步）。"""

    def __init__(self, repo_ref: RepoRef, token: str = ""):
        self.ref = repo_ref
        self.token = token or get_token(repo_ref.platform)
        self._client = httpx.Client(
            base_url=repo_ref.base_url,
            headers=self._headers(),
            timeout=30,
        )

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            if self.ref.platform == "github":
                h["Authorization"] = f"Bearer {self.token}"
            else:
                h["PRIVATE-TOKEN"] = self.token
        return h

    def close(self) -> None:
        self._client.close()

    # ── PR 列表 ──

    def list_prs(self, state: str = "open") -> list[PRInfo]:
        """列出 PR（GitHub）或 MR（GitLab）。"""
        if self.ref.platform == "github":
            return self._list_github_prs(state)
        return self._list_gitlab_mrs(state)

    def _list_github_prs(self, state: str) -> list[PRInfo]:
        path = f"/repos/{self.ref.owner}/{self.ref.repo}/pulls"
        resp = self._client.get(path, params={"state": state, "per_page": 30})
        resp.raise_for_status()
        return [_parse_github_pr(item) for item in resp.json()]

    def _list_gitlab_mrs(self, state: str) -> list[PRInfo]:
        pid = f"{self.ref.owner}%2F{self.ref.repo}"
        path = f"/projects/{pid}/merge_requests"
        resp = self._client.get(path, params={"state": state, "per_page": 30})
        if resp.status_code == 404:
            # 尝试用项目 ID
            raise ValueError(f"GitLab project not found: {self.ref.owner}/{self.ref.repo}")
        resp.raise_for_status()
        return [_parse_gitlab_mr(item) for item in resp.json()]

    # ── PR 详情 + Diff ──

    def get_pr_detail(self, number: int) -> PRDetail:
        """获取 PR 详情（含 diff 和变更文件）。"""
        if self.ref.platform == "github":
            return self._get_github_pr_detail(number)
        return self._get_gitlab_mr_detail(number)

    def _get_github_pr_detail(self, number: int) -> PRDetail:
        path = f"/repos/{self.ref.owner}/{self.ref.repo}/pulls/{number}"
        resp = self._client.get(path)
        resp.raise_for_status()
        pr = resp.json()
        info = _parse_github_pr(pr)

        # 获取 diff
        diff_resp = self._client.get(
            path,
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        raw_diff = diff_resp.text if diff_resp.status_code == 200 else ""

        # 获取变更文件
        files_resp = self._client.get(f"{path}/files")
        files_data = files_resp.json() if files_resp.status_code == 200 else []

        return _build_pr_detail(info, raw_diff, files_data, "github")

    def _get_gitlab_mr_detail(self, number: int) -> PRDetail:
        pid = f"{self.ref.owner}%2F{self.ref.repo}"
        path = f"/projects/{pid}/merge_requests/{number}"
        resp = self._client.get(path)
        resp.raise_for_status()
        mr = resp.json()
        info = _parse_gitlab_mr(mr)

        # 获取 diff
        changes_path = f"{path}/changes"
        changes_resp = self._client.get(changes_path)
        changes_data = changes_resp.json() if changes_resp.status_code == 200 else {}

        raw_diff = ""
        files_data = changes_data.get("changes", [])
        for ch in files_data:
            raw_diff += ch.get("diff", "")

        return _build_pr_detail(info, raw_diff, files_data, "gitlab")


# ── 解析辅助 ──


def _parse_github_pr(item: dict) -> PRInfo:
    head = item.get("head", {})
    base = item.get("base", {})
    user = item.get("user", {})
    return PRInfo(
        number=item.get("number", 0),
        title=item.get("title", ""),
        description=item.get("body", "") or "",
        state=item.get("state", "open"),
        source_branch=head.get("ref", ""),
        target_branch=base.get("ref", ""),
        author=user.get("login", ""),
        url=item.get("html_url", ""),
        created_at=item.get("created_at", ""),
        updated_at=item.get("updated_at", ""),
        platform="github",
    )


def _parse_gitlab_mr(item: dict) -> PRInfo:
    author = item.get("author", {})
    return PRInfo(
        number=item.get("iid", 0),
        title=item.get("title", ""),
        description=item.get("description", "") or "",
        state=item.get("state", "opened") if item.get("state") == "opened" else item.get("state", "open"),
        source_branch=item.get("source_branch", ""),
        target_branch=item.get("target_branch", ""),
        author=author.get("username", ""),
        url=item.get("web_url", ""),
        created_at=item.get("created_at", ""),
        updated_at=item.get("updated_at", ""),
        platform="gitlab",
    )


def _build_pr_detail(info: PRInfo, raw_diff: str, files: list[dict], platform: str) -> PRDetail:
    changed_files: list[dict] = []
    total_add = 0
    total_del = 0

    for f in files:
        if platform == "github":
            adds = f.get("additions", 0)
            dels = f.get("deletions", 0)
            changed_files.append({
                "file_path": f.get("filename", ""),
                "change_type": f.get("status", "modified"),
                "additions": adds,
                "deletions": dels,
            })
        else:
            adds = int(f.get("additions", 0) or 0)
            dels = int(f.get("deletions", 0) or 0)
            changed_files.append({
                "file_path": f.get("new_path", ""),
                "change_type": "new" if f.get("new_file") else "deleted" if f.get("deleted_file") else "modified",
                "additions": adds,
                "deletions": dels,
            })
        total_add += adds
        total_del += dels

    return PRDetail(
        number=info.number,
        title=info.title,
        description=info.description,
        state=info.state,
        source_branch=info.source_branch,
        target_branch=info.target_branch,
        author=info.author,
        url=info.url,
        created_at=info.created_at,
        updated_at=info.updated_at,
        platform=info.platform,
        changed_files=changed_files,
        raw_diff=raw_diff,
        total_additions=total_add,
        total_deletions=total_del,
    )
