"""PR / MR 管理 API + Webhook 接收端点。"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from mix_agent.services.git_platform import (
    GitPlatformClient,
    PRInfo,
    PRDetail,
    RepoRef,
    get_token,
    parse_repo_url,
    set_token,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Token 管理
# ═══════════════════════════════════════════════════════════


@router.get("/pr/token")
def get_git_token(platform: str = Query(..., description="github 或 gitlab")) -> dict:
    """获取已配置的 Git 平台 API Token（遮盖显示）。"""
    token = get_token(platform.strip().lower())
    masked = token[:4] + "****" + token[-4:] if len(token) > 8 else "****"
    return {"platform": platform, "has_token": bool(token), "token_masked": masked}


@router.put("/pr/token")
def set_git_token(body: dict) -> dict:
    """设置 Git 平台 API Token。

    Example: PUT /pr/token
    {"platform": "github", "token": "ghp_xxxxxxxxxxxx"}
    """
    platform = body.get("platform", "").strip().lower()
    token = body.get("token", "").strip()
    if not platform:
        return {"ok": False, "error": "Platform is required (github / gitlab)."}
    if platform not in ("github", "gitlab"):
        return {"ok": False, "error": "Platform must be github or gitlab."}
    set_token(platform, token)
    return {"ok": True, "platform": platform}


# ═══════════════════════════════════════════════════════════
# PR 操作 (前端调用)
# ═══════════════════════════════════════════════════════════


@router.get("/pr/list")
def list_prs(
    repo_url: str = Query(..., description="仓库 URL"),
    state: str = Query("open", description="open / closed / all"),
) -> dict:
    """列出仓库的 PR / MR。

    Example: GET /pr/list?repo_url=https://github.com/owner/repo&state=open
    """
    ref = _parse_repo(repo_url)
    client = GitPlatformClient(ref)
    try:
        prs = client.list_prs(state=state)
        return {
            "ok": True,
            "platform": ref.platform,
            "repo": f"{ref.owner}/{ref.repo}",
            "prs": [p.to_dict() for p in prs],
            "total": len(prs),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


@router.get("/pr/{number}")
def get_pr_detail(
    number: int,
    repo_url: str = Query(..., description="仓库 URL"),
) -> dict:
    """获取 PR 详情（含 diff 和变更文件）。

    Example: GET /pr/42?repo_url=https://github.com/owner/repo
    """
    ref = _parse_repo(repo_url)
    client = GitPlatformClient(ref)
    try:
        detail = client.get_pr_detail(number)
        return {
            "ok": True,
            "pr": detail.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


# ═══════════════════════════════════════════════════════════
# Webhook 接收
# ═══════════════════════════════════════════════════════════


@router.post("/webhook/github")
async def github_webhook(request: Request) -> dict:
    """接收 GitHub Webhook — PR opened / synchronize / reopened 事件。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = request.headers.get("X-GitHub-Event", "")
    action = body.get("action", "")

    logger.info(f"[GitHub Webhook] event={event_type} action={action}")

    if event_type != "pull_request":
        return {"ok": True, "skipped": True, "reason": f"Not a PR event: {event_type}"}

    if action not in ("opened", "synchronize", "reopened"):
        return {"ok": True, "skipped": True, "reason": f"PR action skipped: {action}"}

    pr_data = body.get("pull_request", {})
    repo_data = body.get("repository", {})

    pr_info = PRInfo(
        number=pr_data.get("number", 0),
        title=pr_data.get("title", ""),
        description=pr_data.get("body", "") or "",
        state=pr_data.get("state", "open"),
        source_branch=pr_data.get("head", {}).get("ref", ""),
        target_branch=pr_data.get("base", {}).get("ref", ""),
        author=pr_data.get("user", {}).get("login", ""),
        url=pr_data.get("html_url", ""),
        created_at=pr_data.get("created_at", ""),
        updated_at=pr_data.get("updated_at", ""),
        platform="github",
    )

    logger.info(
        f"[GitHub Webhook] PR #{pr_info.number}: {pr_info.title} "
        f"({pr_info.source_branch} → {pr_info.target_branch}) action={action}"
    )

    # TODO: 触发代码审查流水线
    # trigger_review(pr_info, repo_data)

    return {
        "ok": True,
        "action": action,
        "pr": pr_info.to_dict(),
        "message": f"PR #{pr_info.number} webhook received",
    }


@router.post("/webhook/gitlab")
async def gitlab_webhook(request: Request) -> dict:
    """接收 GitLab Webhook — Merge Request Hook。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = body.get("object_kind", "")

    logger.info(f"[GitLab Webhook] object_kind={event_type}")

    if event_type != "merge_request":
        return {"ok": True, "skipped": True, "reason": f"Not a MR event: {event_type}"}

    attrs = body.get("object_attributes", {})
    action = attrs.get("action", "")

    if action not in ("open", "update", "reopen"):
        return {"ok": True, "skipped": True, "reason": f"MR action skipped: {action}"}

    pr_info = PRInfo(
        number=attrs.get("iid", 0),
        title=attrs.get("title", ""),
        description=attrs.get("description", "") or "",
        state=attrs.get("state", "opened"),
        source_branch=attrs.get("source_branch", ""),
        target_branch=attrs.get("target_branch", ""),
        author=body.get("user", {}).get("username", ""),
        url=attrs.get("url", ""),
        created_at=attrs.get("created_at", ""),
        updated_at=attrs.get("updated_at", ""),
        platform="gitlab",
    )

    logger.info(
        f"[GitLab Webhook] MR !{pr_info.number}: {pr_info.title} "
        f"({pr_info.source_branch} → {pr_info.target_branch}) action={action}"
    )

    return {
        "ok": True,
        "action": action,
        "pr": pr_info.to_dict(),
        "message": f"MR !{pr_info.number} webhook received",
    }


# ═══════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════


def _parse_repo(url: str) -> RepoRef:
    ref = parse_repo_url(url)
    if not ref:
        raise HTTPException(status_code=400, detail=f"Cannot parse repo URL: {url}")
    return ref
