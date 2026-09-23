"""GitHub integration — scan repos for applicable files and open PRs.

Supports both github.ibm.com (GHE) and github.com (public) repos.
CICS/* repos are assumed to be on github.ibm.com; IBM/* on github.com.

Also contains small helpers used by the MCP tools:
  - build_file_context()  — format fetched file contents for Bob to read
  - AnnouncementAnalysis  — dataclass Bob populates when analysing announcements
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from github import Github, GithubException, RateLimitExceededException


_GHE_BASE_URL = "https://github.ibm.com/api/v3"
_PUBLIC_ORGS = {"IBM"}  # orgs that live on github.com
_SCAN_TIMEOUT = 20  # seconds per repo scan before giving up


def _get_client(repo_name: str) -> Github:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN environment variable is not set. "
            "Create a PAT at https://github.ibm.com/settings/tokens with repo scope."
        )
    org = repo_name.split("/")[0]
    if org in _PUBLIC_ORGS:
        return Github(login_or_token=token)
    return Github(base_url=_GHE_BASE_URL, login_or_token=token)


@dataclass
class RepoMatch:
    repo: str          # "CICS/my-repo"
    matched_files: list[str]  # paths of files that matched the patterns
    file_contents: dict[str, str] = field(default_factory=dict)  # path -> content


def _pattern_to_search_terms(pattern: str) -> tuple[str, str | None]:
    """Convert a file pattern to a (filename_term, path_filter) pair for GitHub search.

    GitHub code search `filename:` only matches the basename, not the full path.
    So `scripts/setup.sh` must be searched as `filename:setup.sh` and then
    filtered by path. Glob wildcards like `*` are preserved for fnmatch-style
    matching after results are returned.

    Returns:
        filename_term: the basename to pass to `filename:` (e.g. 'setup.sh')
        path_prefix:   optional path prefix to filter results (e.g. 'scripts/')
                       None means no path filtering needed.
    """
    p = PurePosixPath(pattern)
    basename = p.name          # e.g. 'setup.sh' or '.pipeline-config*.yaml'
    parent = str(p.parent)     # e.g. 'scripts' or '.'
    path_prefix = None if parent == "." else parent + "/"
    return basename, path_prefix


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Check whether a file path returned by GitHub matches the original pattern.

    Handles both plain filenames ('setup.sh'), path-prefixed patterns
    ('scripts/setup.sh'), and glob patterns ('.pipeline-config*.yaml').
    """
    import fnmatch
    basename = PurePosixPath(path).name
    pattern_base = PurePosixPath(pattern).name
    pattern_dir = str(PurePosixPath(pattern).parent)

    # Basename must match (glob-aware)
    if not fnmatch.fnmatch(basename, pattern_base):
        return False

    # If pattern has a path prefix, the file path must contain it
    if pattern_dir and pattern_dir != ".":
        if not path.startswith(pattern_dir + "/") and ("/" + pattern_dir + "/") not in path:
            return False

    return True


def scan_repos(
    repos: list[str],
    file_patterns: list[str],
) -> list[RepoMatch]:
    """
    For each repo, search for files whose paths match any of the given patterns.

    Patterns can be:
      - plain filenames:          'setup.sh'
      - path-prefixed:            'scripts/setup.sh'
      - glob basenames:           '.pipeline-config*.yaml'
      - path + glob:              'scripts/*.sh'

    GitHub code search only supports filename: (basename) matching, so path
    components are applied as a post-search filter.

    Returns only repos where at least one file matched.
    Scans repos in parallel (one thread per repo) with a per-repo timeout.
    """
    def _scan_one(repo_name: str) -> RepoMatch | None:
        gh = _get_client(repo_name)
        try:
            repo = gh.get_repo(repo_name)
        except GithubException:
            return None

        matched_files: list[str] = []
        file_contents: dict[str, str] = {}

        for pattern in file_patterns:
            filename_term, _path_prefix = _pattern_to_search_terms(pattern)
            query = f"filename:{filename_term} repo:{repo_name}"
            try:
                code_results = gh.search_code(query=query)
                for item in code_results:
                    path = item.path
                    # Apply path-prefix and glob filter
                    if not _path_matches_pattern(path, pattern):
                        continue
                    if path not in matched_files:
                        matched_files.append(path)
                        try:
                            file_obj = repo.get_contents(path)
                            if isinstance(file_obj, list):
                                continue
                            content = file_obj.decoded_content.decode("utf-8", errors="replace")
                            file_contents[path] = content
                        except GithubException:
                            pass
            except (GithubException, RateLimitExceededException):
                continue

        if matched_files:
            return RepoMatch(repo=repo_name, matched_files=matched_files, file_contents=file_contents)
        return None

    results: list[RepoMatch] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_scan_one, repo_name): repo_name for repo_name in repos}
        for future in as_completed(futures, timeout=_SCAN_TIMEOUT * len(repos)):
            try:
                result = future.result(timeout=_SCAN_TIMEOUT)
                if result is not None:
                    results.append(result)
            except Exception:
                continue

    return results


def get_file_content(repo_name: str, path: str, ref: str = "main") -> str:
    """Fetch the raw content of a single file from a repo at a given ref."""
    gh = _get_client(repo_name)
    repo = gh.get_repo(repo_name)
    file_obj = repo.get_contents(path, ref=ref)
    if isinstance(file_obj, list):
        raise ValueError(f"{path} is a directory, not a file")
    return file_obj.decoded_content.decode("utf-8", errors="replace")


def search_repo_content(
    repo_name: str,
    content_pattern: str,
    file_extensions: list[str] | None = None,
) -> dict[str, list[tuple[int, str]]]:
    """Search all files in a repo for lines matching a content pattern (regex).

    Uses GitHub code search to find candidate files, then fetches and scans
    each one line-by-line. This allows Bob to find *any* usage of a pattern
    (e.g. 'get_env', 'mend-product-name', a specific variable name) across
    the entire repository regardless of file path.

    Args:
        repo_name:        'ORG/NAME' repository.
        content_pattern:  Regex pattern to search for within file contents.
        file_extensions:  Optional list of extensions to restrict search
                          (e.g. ['.sh', '.yaml']). None = search all files.

    Returns:
        Dict mapping file path -> list of (line_number, line_text) matches.
    """
    gh = _get_client(repo_name)
    try:
        repo = gh.get_repo(repo_name)
    except GithubException:
        return {}

    compiled = re.compile(content_pattern)

    # Build extension filter clause for GitHub search
    ext_clause = ""
    if file_extensions:
        # GitHub search supports 'extension:sh' etc.
        ext_parts = " OR ".join(
            f"extension:{ext.lstrip('.')}" for ext in file_extensions
        )
        ext_clause = f" ({ext_parts})"

    query = f"{content_pattern} repo:{repo_name}{ext_clause}"

    candidate_paths: list[str] = []
    try:
        results = gh.search_code(query=query)
        for item in results:
            candidate_paths.append(item.path)
    except (GithubException, RateLimitExceededException):
        pass

    matches: dict[str, list[tuple[int, str]]] = {}
    for path in candidate_paths:
        try:
            file_obj = repo.get_contents(path)
            if isinstance(file_obj, list):
                continue
            content = file_obj.decoded_content.decode("utf-8", errors="replace")
            hits = [
                (i + 1, line)
                for i, line in enumerate(content.splitlines())
                if compiled.search(line)
            ]
            if hits:
                matches[path] = hits
        except GithubException:
            continue

    return matches


def push_file_changes(
    repo_name: str,
    branch_name: str,
    file_changes: dict[str, str],
    commit_message: str,
) -> dict[str, str]:
    """Push file changes to an existing branch without creating a new PR.

    Used to update files on an already-open PR branch.

    Args:
        repo_name:      'ORG/NAME' repository.
        branch_name:    Existing branch to push to.
        file_changes:   Dict mapping file paths to their complete new content.
        commit_message: Commit message.

    Returns:
        Dict mapping file path -> 'updated' or 'created'.
    """
    gh = _get_client(repo_name)
    repo = gh.get_repo(repo_name)

    results: dict[str, str] = {}
    for file_path, new_content in file_changes.items():
        try:
            existing = repo.get_contents(file_path, ref=branch_name)
            if isinstance(existing, list):
                continue
            repo.update_file(
                path=file_path,
                message=commit_message,
                content=new_content,
                sha=existing.sha,
                branch=branch_name,
            )
            results[file_path] = "updated"
        except GithubException:
            repo.create_file(
                path=file_path,
                message=commit_message,
                content=new_content,
                branch=branch_name,
            )
            results[file_path] = "created"

    return results


def create_pull_request(
    repo_name: str,
    branch_name: str,
    title: str,
    body: str,
    file_changes: dict[str, str],  # path -> new content
    base_branch: str = "main",
) -> str:
    """
    Create a branch, commit file changes, and open a PR.
    Returns the URL of the created PR.
    """
    gh = _get_client(repo_name)
    repo = gh.get_repo(repo_name)

    # Get the SHA of the base branch
    base_ref = repo.get_branch(base_branch)
    base_sha = base_ref.commit.sha

    # Create the new branch
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)

    # Commit each changed file
    for file_path, new_content in file_changes.items():
        try:
            existing = repo.get_contents(file_path, ref=branch_name)
            if isinstance(existing, list):
                continue
            repo.update_file(
                path=file_path,
                message=f"chore: {title}",
                content=new_content,
                sha=existing.sha,
                branch=branch_name,
            )
        except GithubException:
            # File doesn't exist yet — create it
            repo.create_file(
                path=file_path,
                message=f"chore: {title}",
                content=new_content,
                branch=branch_name,
            )

    # Open the PR
    pr = repo.create_pull(
        title=title,
        body=body,
        head=branch_name,
        base=base_branch,
    )
    return pr.html_url


# ---------------------------------------------------------------------------
# File context helper (used by MCP get_repo_files tool)
# ---------------------------------------------------------------------------

def build_file_context(file_contents: dict[str, str]) -> str:
    """Format file contents into a readable block for Bob to analyse."""
    if not file_contents:
        return "No matching files found."
    return "\n\n".join(f"=== {path} ===\n{content}" for path, content in file_contents.items())


# ---------------------------------------------------------------------------
# Announcement analysis dataclass (populated by Bob, not LLM)
# ---------------------------------------------------------------------------

@dataclass
class AnnouncementAnalysis:
    """Structured representation of a parsed announcement — populated by Bob."""
    category: str = ""
    summary: str = ""
    file_patterns: list[str] = field(default_factory=list)
    suggested_change: str = ""
    action_required: bool = True
    raw_message: str = ""
    channel: str = ""
    permalink: str = ""
