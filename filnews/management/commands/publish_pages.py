"""Build the static site and commit it onto a dedicated git branch.

The branch only holds the generated files (no source code) and is meant to be
served by a static host (GitHub Pages, Cloudflare Pages, a `git pull` on a
server...). The commit is made with git plumbing and a temporary index: the
working tree and the current branch are never touched.
"""

import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


def git(
    *args: str, cwd: Path, env: dict | None = None, input: str | None = None
) -> str:
    try:
        result = subprocess.run(  # noqa: S603 (fixed git arguments)
            ["git", *args],  # noqa: S607
            cwd=cwd,
            env=env,
            input=input,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise CommandError(
            f"git {' '.join(args)} failed: {error.stderr.strip()}"
        ) from None
    return result.stdout.strip()


def branch_head(repo: Path, branch: str) -> str | None:
    try:
        return git(
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}^{{commit}}",
            cwd=repo,
        )
    except CommandError:
        return None


def write_host_files(output: Path) -> None:
    """Files expected by static hosts, at the root of the published site."""
    # GitHub Pages: serve files as-is (no Jekyll), on the custom domain.
    (output / ".nojekyll").write_text("")
    host = urlparse(settings.SITE_URL).hostname
    if host and host not in {"localhost", "127.0.0.1"}:
        (output / "CNAME").write_text(f"{host}\n")


def commit_directory(
    repo: Path, directory: Path, branch: str, message: str
) -> str | None:
    """Commit the content of `directory` as the new tip of `branch` in `repo`.

    Returns the new commit, or None when the content did not change.
    """
    parent = branch_head(repo, branch)
    git_dir = git("rev-parse", "--absolute-git-dir", cwd=repo)
    with tempfile.TemporaryDirectory(prefix="filnews-index-") as tmp:
        env = {
            **os.environ,
            "GIT_DIR": git_dir,
            "GIT_WORK_TREE": str(directory),
            "GIT_INDEX_FILE": str(Path(tmp) / "index"),
        }
        git("add", "--all", "--force", ".", cwd=directory, env=env)
        tree = git("write-tree", cwd=directory, env=env)

    if parent and git("rev-parse", f"{parent}^{{tree}}", cwd=repo) == tree:
        return None
    parent_args = ["-p", parent] if parent else []
    commit = git("commit-tree", tree, *parent_args, cwd=repo, input=message)
    old_value = [parent] if parent else []
    git("update-ref", f"refs/heads/{branch}", commit, *old_value, cwd=repo)
    return commit


class Command(BaseCommand):
    help = (
        "Build the static site and commit it onto a git branch "
        "(default: pages), ready to be pushed to a static host."
    )

    def add_arguments(self, parser):
        parser.add_argument("--branch", default="pages")
        parser.add_argument(
            "--push",
            action="store_true",
            help="Push the branch to the remote after the commit.",
        )
        parser.add_argument("--remote", default="origin")
        parser.add_argument(
            "--skip-build",
            action="store_true",
            help="Publish the existing dist/ directory without rebuilding it.",
        )

    def handle(
        self, *args, branch: str, push: bool, remote: str, skip_build: bool, **options
    ):
        repo = settings.BASE_DIR
        if git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo) == branch:
            raise CommandError(f"The checked out branch is '{branch}': switch first.")

        output = Path(settings.DIST_DIR).resolve()
        if not skip_build:
            call_command("build_site", output=output, stdout=self.stdout)
        elif not (output / "index.html").is_file():
            raise CommandError(f"No built site in {output}: run build_site first.")
        write_host_files(output)

        source = git("rev-parse", "--short", "HEAD", cwd=repo)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        message = f"Publish {settings.SITE_URL} ({now}, from {source})\n"
        commit = commit_directory(repo, output, branch, message)
        if commit is None:
            self.stdout.write(f"Branch '{branch}' already up to date.")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Committed {commit[:10]} on branch '{branch}'.")
            )

        if push:
            git("push", remote, f"refs/heads/{branch}:refs/heads/{branch}", cwd=repo)
            self.stdout.write(self.style.SUCCESS(f"Pushed '{branch}' to {remote}."))
        else:
            self.stdout.write(f"To put it online: git push {remote} {branch}")
