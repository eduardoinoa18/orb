"""GitHub integration client for ORB Platform.

Allows Commander and agents to:
- Create issues and PRs
- Read and comment on issues
- Check repo status and recent commits
- Create gists (code snippets)
- Manage repo labels
- Read CI/CD workflow statuses

Requires: GITHUB_TOKEN (Personal Access Token or Fine-Grained) in Railway env vars.
Free tier: 5,000 API requests/hour.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger("orb.integrations.github")

GITHUB_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    from config.settings import get_settings
    token = get_settings().resolve("github_token")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not configured.")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def is_github_available() -> bool:
    try:
        from config.settings import get_settings
        return get_settings().is_configured("github_token")
    except Exception:
        return False


def _request(method: str, path: str, body: dict | None = None) -> Any:
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_text = e.read().decode()
        logger.error("GitHub API %s %s failed: %s", method, path, error_text)
        raise RuntimeError(f"GitHub API error {e.code}: {error_text[:200]}") from e
    except Exception as e:
        raise RuntimeError(f"GitHub error: {e}") from e


def get_authenticated_user() -> dict[str, Any]:
    """Get the currently authenticated GitHub user."""
    return _request("GET", "/user")


def list_repos(owner: str | None = None) -> list[dict[str, Any]]:
    """List repos for the authenticated user or a specific owner."""
    path = f"/users/{owner}/repos" if owner else "/user/repos"
    repos = _request("GET", f"{path}?per_page=50&sort=updated")
    return [
        {
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "description": r.get("description", ""),
            "private": r.get("private"),
            "url": r.get("html_url"),
            "stars": r.get("stargazers_count", 0),
            "default_branch": r.get("default_branch", "main"),
            "updated_at": r.get("updated_at"),
        }
        for r in (repos if isinstance(repos, list) else [])
    ]


def get_recent_commits(
    owner: str,
    repo: str,
    branch: str = "main",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get recent commits from a repository."""
    commits = _request("GET", f"/repos/{owner}/{repo}/commits?sha={branch}&per_page={limit}")
    return [
        {
            "sha": c.get("sha", "")[:7],
            "message": (c.get("commit", {}).get("message") or "").split("\n")[0],
            "author": c.get("commit", {}).get("author", {}).get("name", ""),
            "date": c.get("commit", {}).get("author", {}).get("date", ""),
            "url": c.get("html_url", ""),
        }
        for c in (commits if isinstance(commits, list) else [])
    ]


def create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new GitHub issue.

    Returns: {number, url, title}
    """
    payload: dict[str, Any] = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees

    issue = _request("POST", f"/repos/{owner}/{repo}/issues", payload)
    logger.info("GitHub issue created: #%s %s", issue.get("number"), title)
    return {
        "number": issue.get("number"),
        "url": issue.get("html_url"),
        "title": issue.get("title"),
    }


def comment_on_issue(
    owner: str,
    repo: str,
    issue_number: int,
    comment: str,
) -> dict[str, Any]:
    """Add a comment to an existing issue or PR."""
    result = _request(
        "POST",
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"body": comment},
    )
    return {"id": result.get("id"), "url": result.get("html_url")}


def list_open_issues(
    owner: str,
    repo: str,
    label: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List open issues in a repo, optionally filtered by label."""
    path = f"/repos/{owner}/{repo}/issues?state=open&per_page={limit}"
    if label:
        path += f"&labels={label}"
    issues = _request("GET", path)
    return [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "url": i.get("html_url"),
            "labels": [lb.get("name") for lb in i.get("labels", [])],
            "assignees": [a.get("login") for a in i.get("assignees", [])],
            "created_at": i.get("created_at"),
        }
        for i in (issues if isinstance(issues, list) else [])
    ]


def get_workflow_runs(
    owner: str,
    repo: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Get recent CI/CD workflow runs."""
    result = _request("GET", f"/repos/{owner}/{repo}/actions/runs?per_page={limit}")
    runs = result.get("workflow_runs", []) if isinstance(result, dict) else []
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "branch": r.get("head_branch"),
            "url": r.get("html_url"),
            "started_at": r.get("run_started_at"),
        }
        for r in runs
    ]


def create_gist(
    description: str,
    files: dict[str, str],
    public: bool = False,
) -> dict[str, Any]:
    """Create a GitHub Gist for sharing code snippets.

    Args:
        description: Gist description.
        files: {filename: content}
        public: Whether the gist is public (default False).

    Returns: {id, url}
    """
    payload = {
        "description": description,
        "public": public,
        "files": {name: {"content": content} for name, content in files.items()},
    }
    result = _request("POST", "/gists", payload)
    return {"id": result.get("id"), "url": result.get("html_url")}


def test_connection() -> tuple[bool, str]:
    """Verify GitHub token by calling the user endpoint."""
    try:
        user = get_authenticated_user()
        return True, f"Connected as @{user.get('login', 'unknown')}"
    except Exception as e:
        return False, f"GitHub connection failed: {e}"
