"""GitHub client wrapping PyGithub and GitPython."""

import os
import re
import tempfile
from pathlib import Path

from github import Github, GithubException, InputGitTreeElement
from github.Repository import Repository
from github.PullRequest import PullRequest
from git import Repo as GitRepo
from git.exc import GitCommandError

from patcher.github.models import (
    IssueData,
    PRData,
    FileChange,
    CIResult,
    CICheck,
    CIStatus,
    ReviewComment,
)


class GitHubClientError(Exception):
    """Raised when GitHub operations fail."""


class GitHubClient:
    """Unified GitHub client wrapping PyGithub and GitPython."""

    def __init__(
        self,
        token: str | None = None,
        repo_name: str | None = None,
    ):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise GitHubClientError(
                "GitHub token not found. Set GITHUB_TOKEN environment variable."
            )

        self._github = Github(self.token)
        self._repo_name = repo_name
        self._repo: Repository | None = None

        # GitPython local repo
        self._local_repo: GitRepo | None = None
        self._local_path: Path | None = None

    # ------------------------------------------------------------------
    # Repository helpers
    # ------------------------------------------------------------------

    @property
    def repo(self) -> Repository:
        if self._repo is None:
            if not self._repo_name:
                raise GitHubClientError("Repository name not set.")
            try:
                self._repo = self._github.get_repo(self._repo_name)
            except GithubException as e:
                raise GitHubClientError(f"Failed to get repository: {e}") from e
        return self._repo

    def set_repo(self, repo_name: str) -> None:
        self._repo_name = repo_name
        self._repo = None

    @property
    def local_path(self) -> Path | None:
        """Get path to local clone if available."""
        return self._local_path

    @property
    def default_branch(self) -> str:
        """Get the repository's default branch name."""
        return self.repo.default_branch

    # ------------------------------------------------------------------
    # Local Repository (GitPython)
    # ------------------------------------------------------------------

    def clone_repo(self, path: Path | None = None) -> Path:
        """Clone the repository to a local path.

        Args:
            path: Local path to clone to. Defaults to temp directory.

        Returns:
            Path to the cloned repository
        """
        if self._local_path is not None and self._local_path.exists():
            return self._local_path

        if path is None:
            path = Path(tempfile.mkdtemp(prefix="patcher_"))

        try:
            clone_url = f"https://x-access-token:{self.token}@github.com/{self._repo_name}.git"
            self._local_repo = GitRepo.clone_from(clone_url, path)
            self._local_path = path
            return path
        except GitCommandError as e:
            raise GitHubClientError(f"Failed to clone repository: {e}") from e

    def pull_latest(self, branch: str | None = None) -> None:
        """Pull latest changes from remote.

        Args:
            branch: Branch to pull. If None, pulls current branch.
        """
        if self._local_repo is None:
            raise GitHubClientError("Repository not cloned. Call clone_repo first.")

        try:
            origin = self._local_repo.remotes.origin
            origin.fetch()

            if branch:
                # Check if branch exists locally
                local_branches = [b.name for b in self._local_repo.branches]
                if branch in local_branches:
                    self._local_repo.heads[branch].checkout()
                else:
                    # Create local tracking branch from remote
                    remote_ref = origin.refs[branch]
                    local_branch = self._local_repo.create_head(branch, remote_ref)
                    local_branch.set_tracking_branch(remote_ref)
                    local_branch.checkout()

                origin.pull(branch)
            else:
                origin.pull()
        except GitCommandError as e:
            raise GitHubClientError(f"Failed to pull latest: {e}") from e

    def checkout_branch(self, branch: str, create: bool = False) -> None:
        """Checkout a branch in local repo.

        Args:
            branch: Branch name
            create: Whether to create the branch if it doesn't exist
        """
        if self._local_repo is None:
            raise GitHubClientError("Repository not cloned. Call clone_repo first.")

        try:
            if create:
                new_branch = self._local_repo.create_head(branch)
                new_branch.checkout()
            else:
                self._local_repo.heads[branch].checkout()
        except GitCommandError as e:
            raise GitHubClientError(f"Failed to checkout branch {branch}: {e}") from e

    # ------------------------------------------------------------------
    # Issues / PRs
    # ------------------------------------------------------------------

    def get_issue(self, issue_number: int) -> IssueData:
        try:
            issue = self.repo.get_issue(number=issue_number)
            return IssueData(
                number=issue.number,
                title=issue.title,
                body=issue.body or "",
                labels=[label.name for label in issue.labels],
                state=issue.state,
                url=issue.html_url,
                created_at=issue.created_at,
                updated_at=issue.updated_at,
            )
        except GithubException as e:
            raise GitHubClientError(f"Failed to get issue #{issue_number}: {e}") from e

    def get_pr(self, pr_number: int) -> PRData:
        try:
            pr: PullRequest = self.repo.get_pull(number=pr_number)
            return PRData(
                number=pr.number,
                title=pr.title,
                body=pr.body or "",
                head_branch=pr.head.ref,
                base_branch=pr.base.ref,
                labels=[label.name for label in pr.labels],
                state=pr.state,
                url=pr.html_url,
                mergeable=pr.mergeable,
                draft=pr.draft,
                created_at=pr.created_at,
                updated_at=pr.updated_at,
            )
        except GithubException as e:
            raise GitHubClientError(f"Failed to get PR #{pr_number}: {e}") from e

    def get_pr_files(self, pr_number: int) -> list[FileChange]:
        try:
            pr = self.repo.get_pull(number=pr_number)
            return [
                FileChange(
                    path=f.filename,
                    content=f.patch or "",
                    status=f.status,
                )
                for f in pr.get_files()
            ]
        except GithubException as e:
            raise GitHubClientError(
                f"Failed to get files for PR #{pr_number}: {e}"
            ) from e

    def update_pr(
        self,
        pr_number: int,
        title: str | None = None,
        body: str | None = None,
    ) -> None:
        """Update a pull request.

        Args:
            pr_number: PR number
            title: New title (optional)
            body: New body (optional)
        """
        try:
            pr = self.repo.get_pull(number=pr_number)
            kwargs = {}
            if title is not None:
                kwargs["title"] = title
            if body is not None:
                kwargs["body"] = body
            if kwargs:
                pr.edit(**kwargs)
        except GithubException as e:
            raise GitHubClientError(f"Failed to update PR #{pr_number}: {e}") from e

    # ------------------------------------------------------------------
    # CI STATUS (ИСПРАВЛЕНО)
    # ------------------------------------------------------------------

    def get_ci_status(self, pr_number: int) -> CIResult:
        """
        Get CI job results for a PR.

        Correctly handles PyGithub CheckRun / CheckRunOutput objects.
        """
        try:
            pr = self.repo.get_pull(number=pr_number)

            commits = list(pr.get_commits())
            if not commits:
                return CIResult(status=CIStatus.PENDING, checks=[])

            commit = commits[-1]  # последний commit
            check_runs = commit.get_check_runs()

            checks: list[CICheck] = []
            overall_status = CIStatus.SUCCESS

            for run in check_runs:
                # --- determine status ---
                if run.status != "completed":
                    status = CIStatus.PENDING
                    overall_status = CIStatus.PENDING
                else:
                    match run.conclusion:
                        case "success":
                            status = CIStatus.SUCCESS
                        case "failure":
                            status = CIStatus.FAILURE
                            overall_status = CIStatus.FAILURE
                        case "cancelled":
                            status = CIStatus.CANCELLED
                        case "skipped":
                            status = CIStatus.CANCELLED
                        case _:
                            status = CIStatus.ERROR
                            overall_status = CIStatus.ERROR

                # --- extract output safely ---
                output_summary = None
                if run.output:
                    output_summary = run.output.summary or run.output.text

                checks.append(
                    CICheck(
                        name=run.name,
                        status=status,
                        conclusion=run.conclusion,
                        url=run.html_url,
                        output=output_summary,
                    )
                )

            return CIResult(status=overall_status, checks=checks)

        except GithubException as e:
            raise GitHubClientError(
                f"Failed to get CI status for PR #{pr_number}: {e}"
            ) from e

    # ------------------------------------------------------------------
    # Comments / Reviews
    # ------------------------------------------------------------------

    def post_comment(self, issue_or_pr_number: int, body: str) -> None:
        try:
            issue = self.repo.get_issue(number=issue_or_pr_number)
            issue.create_comment(body)
        except GithubException as e:
            raise GitHubClientError(
                f"Failed to post comment on #{issue_or_pr_number}: {e}"
            ) from e

    def post_review(
        self,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
        comments: list[ReviewComment] | None = None,
    ) -> None:
        try:
            pr = self.repo.get_pull(number=pr_number)

            review_comments = []
            if comments:
                for c in comments:
                    if c.path and c.line:
                        review_comments.append(
                            {
                                "path": c.path,
                                "line": c.line,
                                "body": c.body,
                            }
                        )

            # PyGithub requires comments to be a list or omitted, not None
            if review_comments:
                pr.create_review(
                    body=body,
                    event=event,
                    comments=review_comments,
                )
            else:
                pr.create_review(
                    body=body,
                    event=event,
                )
        except GithubException as e:
            raise GitHubClientError(f"Failed to post review on PR #{pr_number}: {e}") from e

    # ------------------------------------------------------------------
    # File Operations (GitHub API)
    # ------------------------------------------------------------------

    def get_file_content(self, path: str, ref: str | None = None) -> str:
        """Get content of a file from the repository.

        Args:
            path: File path in the repository
            ref: Git reference (branch, tag, commit). Defaults to repo's default branch.

        Returns:
            File content as string
        """
        try:
            if ref is None:
                ref = self.default_branch

            content = self.repo.get_contents(path, ref=ref)
            if isinstance(content, list):
                raise GitHubClientError(f"Path '{path}' is a directory, not a file")
            decoded = content.decoded_content
            return decoded.decode("utf-8")
        except GithubException as e:
            raise GitHubClientError(f"Failed to get file '{path}': {e}") from e

    def list_files(self, path: str = "", ref: str | None = None) -> list[str]:
        """List files in a directory.

        Args:
            path: Directory path (empty for root)
            ref: Git reference. Defaults to repo's default branch.

        Returns:
            List of file paths
        """
        try:
            if ref is None:
                ref = self.default_branch

            contents = self.repo.get_contents(path, ref=ref)
            if not isinstance(contents, list):
                contents = [contents]

            files: list[str] = []
            for item in contents:
                if item.type == "file":
                    files.append(item.path)
                elif item.type == "dir":
                    files.append(item.path + "/")

            return sorted(files)
        except GithubException as e:
            raise GitHubClientError(f"Failed to list files in '{path}': {e}") from e

    def get_pr_diff(self, pr_number: int) -> str:
        """Get the diff of a pull request.

        Args:
            pr_number: PR number

        Returns:
            Diff as string
        """
        try:
            pr = self.repo.get_pull(number=pr_number)
            # Get diff via files
            files = pr.get_files()
            diff_parts: list[str] = []

            for f in files:
                diff_parts.append(f"--- a/{f.filename}")
                diff_parts.append(f"+++ b/{f.filename}")
                if f.patch:
                    diff_parts.append(f.patch)
                diff_parts.append("")

            return "\n".join(diff_parts)
        except GithubException as e:
            raise GitHubClientError(f"Failed to get diff for PR #{pr_number}: {e}") from e

    # ------------------------------------------------------------------
    # Branch & Commit Operations (GitHub API)
    # ------------------------------------------------------------------

    def create_branch(self, branch_name: str, from_ref: str | None = None) -> None:
        """Create a new branch via GitHub API.

        Args:
            branch_name: Name of the new branch
            from_ref: Reference to create branch from. Defaults to repo's default branch.
        """
        try:
            if from_ref is None:
                from_ref = self.default_branch

            source = self.repo.get_branch(from_ref)
            self.repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source.commit.sha,
            )
        except GithubException as e:
            if "Reference already exists" in str(e):
                return  # Branch already exists, that's fine
            raise GitHubClientError(f"Failed to create branch '{branch_name}': {e}") from e

    def commit_changes(
        self,
        files: dict[str, str],
        message: str,
        branch: str,
    ) -> str:
        """Commit file changes via GitHub API.

        Args:
            files: Dictionary of file path -> content
            message: Commit message
            branch: Branch to commit to

        Returns:
            Commit SHA
        """
        try:
            # Get the current commit SHA for the branch
            ref = self.repo.get_git_ref(f"heads/{branch}")
            base_sha = ref.object.sha
            base_commit = self.repo.get_git_commit(base_sha)
            base_tree = base_commit.tree

            # Create tree elements for new/modified files
            tree_elements: list[InputGitTreeElement] = []
            for file_path, content in files.items():
                blob = self.repo.create_git_blob(content, "utf-8")
                tree_elements.append(
                    InputGitTreeElement(
                        path=file_path,
                        mode="100644",
                        type="blob",
                        sha=blob.sha,
                    )
                )

            # Create new tree
            new_tree = self.repo.create_git_tree(tree_elements, base_tree)

            # Create commit
            new_commit = self.repo.create_git_commit(
                message=message,
                tree=new_tree,
                parents=[base_commit],
            )

            # Update branch reference
            ref.edit(new_commit.sha)

            return new_commit.sha
        except GithubException as e:
            raise GitHubClientError(f"Failed to commit changes: {e}") from e

    def create_pull_request(
        self,
        title: str,
        body: str,
        head: str,
        base: str | None = None,
        labels: list[str] | None = None,
    ) -> PRData:
        """Create a pull request.

        Args:
            title: PR title
            body: PR body/description
            head: Head branch
            base: Base branch. Defaults to repo's default branch.
            labels: Labels to add

        Returns:
            PRData for the created PR
        """
        try:
            if base is None:
                base = self.default_branch

            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
            )

            # Add labels if specified
            if labels:
                pr.add_to_labels(*labels)

            return PRData(
                number=pr.number,
                title=pr.title,
                body=pr.body or "",
                head_branch=pr.head.ref,
                base_branch=pr.base.ref,
                labels=[label.name for label in pr.labels],
                state=pr.state,
                url=pr.html_url,
                mergeable=pr.mergeable,
                draft=pr.draft,
                created_at=pr.created_at,
                updated_at=pr.updated_at,
            )
        except GithubException as e:
            raise GitHubClientError(f"Failed to create pull request: {e}") from e

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def parse_issue_url(url: str) -> tuple[str, int]:
        match = re.search(r"github\.com/([^/]+/[^/]+)/issues/(\d+)", url)
        if not match:
            raise GitHubClientError(f"Invalid GitHub issue URL: {url}")
        return match.group(1), int(match.group(2))

    @staticmethod
    def parse_pr_url(url: str) -> tuple[str, int]:
        match = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
        if not match:
            raise GitHubClientError(f"Invalid GitHub PR URL: {url}")
        return match.group(1), int(match.group(2))
