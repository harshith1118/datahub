"""PyGithub wrapper for git branching, committing, and pull request creation."""

import logging
import os

from github import Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for automating GitHub PRs from SQL fix commits.

    Args:
        token: GitHub personal access token. Falls back to GITHUB_TOKEN env var.
        repo_name: Target repo in ``owner/repo`` format. Falls back to
            GITHUB_REPO env var.
        dry_run: When True, log intended actions without calling the GitHub API.
    """

    def __init__(
        self,
        token: str | None = None,
        repo_name: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo_name = repo_name or os.environ.get("GITHUB_REPO", "")
        self.dry_run = dry_run
        self._current_branch: str | None = None
        self._github: Github | None = None
        self._repo = None

    def _connect(self):
        """Lazily authenticate and fetch the repository object."""
        if self._repo is not None:
            return self._repo
        if not self.token:
            raise RuntimeError(
                "GITHUB_TOKEN not set. Provide it via the constructor or "
                "the GITHUB_TOKEN environment variable."
            )
        if not self.repo_name:
            raise RuntimeError(
                "GITHUB_REPO not set. Provide it via the constructor or "
                "the GITHUB_REPO environment variable (format: owner/repo)."
            )
        self._github = Github(self.token)
        self._repo = self._github.get_repo(self.repo_name)
        logger.debug("Connected to repo %s", self.repo_name)
        return self._repo

    def create_branch(
        self, base: str = "main", branch_name: str = "fix/datahub-schema-remediation"
    ) -> str:
        """Create a new branch from *base* and return the branch name."""
        self._current_branch = branch_name

        if self.dry_run:
            logger.info(
                "[DRY-RUN] create_branch(base=%s, branch_name=%s)", base, branch_name
            )
            return branch_name

        repo = self._connect()
        try:
            source_branch = repo.get_branch(base)
            sha = source_branch.commit.sha
        except GithubException:
            logger.warning("Base branch '%s' not found, trying 'master'", base)
            source_branch = repo.get_branch("master")
            sha = source_branch.commit.sha

        ref = repo.create_git_ref(f"refs/heads/{branch_name}", sha)
        logger.info("Created branch '%s' from '%s' (sha=%s)", branch_name, base, sha)
        return ref.ref

    def commit_file(
        self,
        file_path: str,
        content: str,
        message: str,
        branch: str | None = None,
    ) -> str:
        """Commit a file to the current branch and return the commit SHA.

        Args:
            file_path: Path within the repo (e.g. ``models/staging/stg_users.sql``).
            content: File content as a string.
            message: Commit message.
            branch: Target branch. Defaults to the branch created by
                :meth:`create_branch`, or ``fix/datahub-schema-remediation``.
        """
        branch = branch or self._current_branch or "fix/datahub-schema-remediation"

        if self.dry_run:
            logger.info(
                "[DRY-RUN] commit_file(path=%s, branch=%s, message=%s)",
                file_path,
                branch,
                message,
            )
            return "DRY_RUN_SHA"

        repo = self._connect()
        result = repo.create_file(file_path, message, content, branch=branch)
        commit_sha: str = result["commit"].sha
        logger.info("Committed %s -> %s (%s)", file_path, branch, commit_sha)
        return commit_sha

    def create_pr(
        self,
        title: str,
        body: str,
        head: str | None = None,
        base: str = "main",
    ) -> str:
        """Open a pull request and return the PR URL.

        Args:
            title: PR title.
            body: PR description body.
            head: The branch with changes. Defaults to the branch created by
                :meth:`create_branch`, or ``fix/datahub-schema-remediation``.
            base: The target branch for the merge (default ``main``).

        Returns:
            The URL of the created pull request.
        """
        head = head or self._current_branch or "fix/datahub-schema-remediation"

        if self.dry_run:
            logger.info(
                "[DRY-RUN] create_pr(title=%s, head=%s, base=%s)", title, head, base
            )
            return f"https://github.com/{self.repo_name}/pull/DRY_RUN"

        repo = self._connect()
        pr = repo.create_pull(base=base, head=head, title=title, body=body)
        logger.info("Created PR #%d -> %s", pr.number, pr.html_url)
        return str(pr.html_url)