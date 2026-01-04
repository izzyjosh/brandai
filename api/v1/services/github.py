from datetime import datetime
from typing import Optional, List, Dict, Any
import httpx
from fastapi import HTTPException, status
from api.v1.utils.encryption import decrypt_token
from api.v1.utils.logger import get_logger

logger = get_logger("github_service")

GITHUB_API_BASE = "https://api.github.com"


class GitHubService:
    """Service class for GitHub API operations."""

    @staticmethod
    async def _make_github_request(
        token: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
    ) -> Dict[str, Any]:
        """
        Make an authenticated request to GitHub API.

        :param token: Decrypted GitHub access token
        :param endpoint: API endpoint (relative to base URL)
        :param params: Query parameters
        :param method: HTTP method
        :return: JSON response data
        """
        url = f"{GITHUB_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            try:
                if method == "GET":
                    response = await client.get(
                        url, headers=headers, params=params, timeout=30.0
                    )
                elif method == "POST":
                    response = await client.post(
                        url, headers=headers, json=params, timeout=30.0
                    )
                else:
                    response = await client.request(
                        method, url, headers=headers, params=params, timeout=30.0
                    )

                # Handle rate limiting
                if (
                    response.status_code == 403
                    and "rate limit" in response.text.lower()
                ):
                    logger.warning("GitHub API rate limit exceeded")
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="GitHub API rate limit exceeded. Please try again later.",
                    )

                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.error("GitHub API authentication failed")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="GitHub token is invalid or expired",
                    )
                logger.error(
                    "GitHub API error",
                    extra={"status_code": e.response.status_code, "error": str(e)},
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"GitHub API error: {str(e)}",
                )
            except httpx.HTTPError as e:
                logger.error("GitHub API request failed", extra={"error": str(e)})
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to communicate with GitHub API",
                )

    @staticmethod
    async def _get_all_pages(
        token: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all pages of results from GitHub API.

        :param token: Decrypted GitHub access token
        :param endpoint: API endpoint
        :param params: Query parameters
        :param max_pages: Maximum number of pages to fetch
        :return: List of all items from all pages
        """
        all_items = []
        page = 1
        per_page = 100  # Maximum allowed by GitHub

        while page <= max_pages:
            page_params = params.copy() if params else {}
            page_params["page"] = page
            page_params["per_page"] = per_page

            items = await GitHubService._make_github_request(
                token, endpoint, page_params
            )

            if not items:
                break

            all_items.extend(items)

            # If we got fewer items than per_page, we've reached the end
            if len(items) < per_page:
                break

            page += 1

        return all_items

    @staticmethod
    async def get_user_repos(
        encrypted_token: str,
        since: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Fetch user repositories.

        :param encrypted_token: Encrypted GitHub access token
        :param since: Filter repos updated after this date
        :param page: Page number
        :param per_page: Items per page
        :return: List of repositories
        """
        token = decrypt_token(encrypted_token)
        params = {
            "page": page,
            "per_page": per_page,
            "sort": "updated",
            "direction": "desc",
        }

        if since:
            params["since"] = since.isoformat()

        repos = await GitHubService._make_github_request(token, "/user/repos", params)
        return repos if isinstance(repos, list) else [repos]

    @staticmethod
    async def get_pushes(
        encrypted_token: str,
        repo: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Fetch push events.

        :param encrypted_token: Encrypted GitHub access token
        :param repo: Repository name (format: owner/repo). If None, fetches from all repos
        :param since: Start date/time
        :param until: End date/time
        :param page: Page number
        :param per_page: Items per page
        :return: List of push events
        """
        token = decrypt_token(encrypted_token)

        if repo:
            # Get push events for a specific repository
            endpoint = f"/repos/{repo}/events"
            params = {"page": page, "per_page": per_page}
            events = await GitHubService._make_github_request(token, endpoint, params)

            # Filter for push events only
            push_events = [e for e in events if e.get("type") == "PushEvent"]

            # Filter by date range
            if since or until:
                filtered_events = []
                for event in push_events:
                    created_at = datetime.fromisoformat(
                        event["created_at"].replace("Z", "+00:00")
                    )
                    if since and created_at < since:
                        continue
                    if until and created_at > until:
                        continue
                    filtered_events.append(event)
                return filtered_events

            return push_events
        else:
            # Get user's recent activity (pushes across all repos)
            # GitHub doesn't have a direct endpoint for this, so we get user events
            endpoint = "/user/events/public"
            params = {"page": page, "per_page": per_page}
            events = await GitHubService._make_github_request(token, endpoint, params)

            # Filter for push events
            push_events = [e for e in events if e.get("type") == "PushEvent"]

            # Filter by date range
            if since or until:
                filtered_events = []
                for event in push_events:
                    created_at = datetime.fromisoformat(
                        event["created_at"].replace("Z", "+00:00")
                    )
                    if since and created_at < since:
                        continue
                    if until and created_at > until:
                        continue
                    filtered_events.append(event)
                return filtered_events

            return push_events

    @staticmethod
    async def get_pull_requests(
        encrypted_token: str,
        repo: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        state: str = "all",
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Fetch pull requests.

        :param encrypted_token: Encrypted GitHub access token
        :param repo: Repository name (format: owner/repo). If None, fetches from all repos
        :param since: Filter PRs created/updated after this date
        :param until: Filter PRs created/updated before this date
        :param state: PR state (open, closed, all)
        :param page: Page number
        :param per_page: Items per page
        :return: List of pull requests
        """
        token = decrypt_token(encrypted_token)

        if repo:
            endpoint = f"/repos/{repo}/pulls"
            params = {
                "state": state,
                "page": page,
                "per_page": per_page,
                "sort": "updated",
                "direction": "desc",
            }
            prs = await GitHubService._make_github_request(token, endpoint, params)

            # Filter by date range
            if since or until:
                filtered_prs = []
                for pr in prs:
                    updated_at = datetime.fromisoformat(
                        pr["updated_at"].replace("Z", "+00:00")
                    )
                    if since and updated_at < since:
                        continue
                    if until and updated_at > until:
                        continue
                    filtered_prs.append(pr)
                return filtered_prs

            return prs
        else:
            # Get PRs from all user repos
            repos = await GitHubService.get_user_repos(
                encrypted_token, page=1, per_page=100
            )
            all_prs = []

            for repo in repos:
                repo_name = repo["full_name"]
                try:
                    repo_prs = await GitHubService.get_pull_requests(
                        encrypted_token,
                        repo=repo_name,
                        since=since,
                        until=until,
                        state=state,
                        page=1,
                        per_page=per_page,
                    )
                    all_prs.extend(repo_prs)
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch PRs for {repo_name}", extra={"error": str(e)}
                    )
                    continue

            # Sort by updated date and apply pagination
            all_prs.sort(
                key=lambda x: datetime.fromisoformat(
                    x["updated_at"].replace("Z", "+00:00")
                ),
                reverse=True,
            )
            start = (page - 1) * per_page
            end = start + per_page
            return all_prs[start:end]

    @staticmethod
    async def get_issues(
        encrypted_token: str,
        repo: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        state: str = "all",
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Fetch issues.

        :param encrypted_token: Encrypted GitHub access token
        :param repo: Repository name (format: owner/repo). If None, fetches from all repos
        :param since: Filter issues created/updated after this date
        :param until: Filter issues created/updated before this date
        :param state: Issue state (open, closed, all)
        :param page: Page number
        :param per_page: Items per page
        :return: List of issues
        """
        token = decrypt_token(encrypted_token)

        if repo:
            endpoint = f"/repos/{repo}/issues"
            params = {
                "state": state,
                "page": page,
                "per_page": per_page,
                "sort": "updated",
                "direction": "desc",
            }
            issues = await GitHubService._make_github_request(token, endpoint, params)

            # Filter out PRs (GitHub API returns PRs in issues endpoint)
            issues = [i for i in issues if "pull_request" not in i]

            # Filter by date range
            if since or until:
                filtered_issues = []
                for issue in issues:
                    updated_at = datetime.fromisoformat(
                        issue["updated_at"].replace("Z", "+00:00")
                    )
                    if since and updated_at < since:
                        continue
                    if until and updated_at > until:
                        continue
                    filtered_issues.append(issue)
                return filtered_issues

            return issues
        else:
            # Get issues from all user repos
            repos = await GitHubService.get_user_repos(
                encrypted_token, page=1, per_page=100
            )
            all_issues = []

            for repo in repos:
                repo_name = repo["full_name"]
                try:
                    repo_issues = await GitHubService.get_issues(
                        encrypted_token,
                        repo=repo_name,
                        since=since,
                        until=until,
                        state=state,
                        page=1,
                        per_page=per_page,
                    )
                    all_issues.extend(repo_issues)
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch issues for {repo_name}",
                        extra={"error": str(e)},
                    )
                    continue

            # Sort by updated date and apply pagination
            all_issues.sort(
                key=lambda x: datetime.fromisoformat(
                    x["updated_at"].replace("Z", "+00:00")
                ),
                reverse=True,
            )
            start = (page - 1) * per_page
            end = start + per_page
            return all_issues[start:end]

    @staticmethod
    async def get_commits(
        encrypted_token: str,
        repo: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        author: Optional[str] = None,
        page: int = 1,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Fetch commit history.

        :param encrypted_token: Encrypted GitHub access token
        :param repo: Repository name (format: owner/repo). If None, fetches from all repos
        :param since: Filter commits after this date
        :param until: Filter commits before this date
        :param author: Filter by author username
        :param page: Page number
        :param per_page: Items per page
        :return: List of commits
        """
        token = decrypt_token(encrypted_token)

        if repo:
            endpoint = f"/repos/{repo}/commits"
            params = {"page": page, "per_page": per_page}

            if since:
                params["since"] = since.isoformat()
            if until:
                params["until"] = until.isoformat()
            if author:
                params["author"] = author

            commits = await GitHubService._make_github_request(token, endpoint, params)
            return commits
        else:
            # Get commits from all user repos
            repos = await GitHubService.get_user_repos(
                encrypted_token, page=1, per_page=100
            )
            all_commits = []

            for repo in repos:
                repo_name = repo["full_name"]
                try:
                    repo_commits = await GitHubService.get_commits(
                        encrypted_token,
                        repo=repo_name,
                        since=since,
                        until=until,
                        author=author,
                        page=1,
                        per_page=per_page,
                    )
                    all_commits.extend(repo_commits)
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch commits for {repo_name}",
                        extra={"error": str(e)},
                    )
                    continue

            # Sort by commit date and apply pagination
            all_commits.sort(
                key=lambda x: datetime.fromisoformat(
                    x["commit"]["author"]["date"].replace("Z", "+00:00")
                ),
                reverse=True,
            )
            start = (page - 1) * per_page
            end = start + per_page
            return all_commits[start:end]

    @staticmethod
    async def get_user_activity(
        encrypted_token: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated user activity across all repositories.

        :param encrypted_token: Encrypted GitHub access token
        :param since: Start date/time
        :param until: End date/time
        :return: Dictionary with aggregated activity data
        """
        # Fetch all activity types
        repos = await GitHubService.get_user_repos(
            encrypted_token, since=since, page=1, per_page=100
        )
        pushes = await GitHubService.get_pushes(
            encrypted_token, since=since, until=until, page=1, per_page=100
        )
        prs = await GitHubService.get_pull_requests(
            encrypted_token, since=since, until=until, state="all", page=1, per_page=100
        )
        issues = await GitHubService.get_issues(
            encrypted_token, since=since, until=until, state="all", page=1, per_page=100
        )
        commits = await GitHubService.get_commits(
            encrypted_token, since=since, until=until, page=1, per_page=100
        )

        return {
            "repositories": len(repos),
            "pushes": len(pushes),
            "pull_requests": len(prs),
            "issues": len(issues),
            "commits": len(commits),
            "repositories_list": [
                {"name": r["full_name"], "updated_at": r["updated_at"]}
                for r in repos[:10]
            ],
            "recent_pushes": pushes[:10],
            "recent_prs": prs[:10],
            "recent_issues": issues[:10],
            "recent_commits": commits[:10],
        }
