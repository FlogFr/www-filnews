import shutil
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from filnews.management.commands.publish_pages import (
    commit_directory,
    git,
    write_host_files,
)


class PublishPagesTests(SimpleTestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="filnews-repo-"))
        self.site = Path(tempfile.mkdtemp(prefix="filnews-site-"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.site, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)  # noqa: S603, S607
        for key, value in [("user.name", "Test"), ("user.email", "t@example.org")]:
            git("config", key, value, cwd=self.repo)
        (self.repo / "README.md").write_text("source\n")
        git("add", "README.md", cwd=self.repo)
        git("commit", "-q", "-m", "init", cwd=self.repo)
        (self.site / "index.html").write_text("<h1>Accueil</h1>")
        (self.site / "static").mkdir()
        (self.site / "static" / "main.css").write_text("body{}")

    def files_on(self, branch: str) -> list[str]:
        return git("ls-tree", "-r", "--name-only", branch, cwd=self.repo).splitlines()

    def test_commits_the_site_without_touching_the_current_branch(self):
        first = commit_directory(self.repo, self.site, "pages", "Publish\n")

        self.assertEqual(self.files_on("pages"), ["index.html", "static/main.css"])
        self.assertEqual(git("rev-parse", "pages", cwd=self.repo), first)
        # Orphan branch: no source code, the checkout is unchanged.
        self.assertEqual(git("rev-list", "--count", "pages", cwd=self.repo), "1")
        self.assertEqual(self.files_on("main"), ["README.md"])
        self.assertEqual(git("status", "--porcelain", cwd=self.repo), "")

        # Same content: nothing to commit. New content: a child commit.
        self.assertIsNone(commit_directory(self.repo, self.site, "pages", "Again\n"))
        (self.site / "static" / "main.css").unlink()
        second = commit_directory(self.repo, self.site, "pages", "Publish\n")
        self.assertEqual(git("rev-parse", f"{second}^", cwd=self.repo), first)
        self.assertEqual(self.files_on("pages"), ["index.html"])

    @override_settings(SITE_URL="https://filnews.fr")
    def test_host_files(self):
        write_host_files(self.site)
        self.assertEqual((self.site / "CNAME").read_text(), "filnews.fr\n")
        self.assertTrue((self.site / ".nojekyll").is_file())
