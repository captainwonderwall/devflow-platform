import os
import stat
import tempfile
import unittest

import sys
_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from build_pr_body import write_create_script


class TestWriteCreateScript(unittest.TestCase):
    def test_creates_executable_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Add new feature", body_path, script_path)
            self.assertTrue(os.path.exists(script_path))
            self.assertTrue(os.access(script_path, os.X_OK))

    def test_script_contains_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("My PR title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn("My PR title", content)

    def test_script_contains_body_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn(body_path, content)

    def test_script_contains_draft_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn("--draft", content)

    def test_script_checks_gh_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn("command -v gh", content)

    def test_script_checks_gh_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn("gh auth status", content)

    def test_script_contains_head_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn('--head "$(git branch --show-current)"', content)

    def test_title_with_shell_metacharacters_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Add $(dangerous) `cmd` feature", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn("'Add $(dangerous) `cmd` feature'", content)

    def test_script_contains_git_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            body_path = os.path.join(tmp, "pr-body.md")
            script_path = os.path.join(tmp, "create-pr.sh")
            write_create_script("Title", body_path, script_path)
            with open(script_path) as f:
                content = f.read()
            self.assertIn("git push -u origin HEAD", content)


if __name__ == "__main__":
    unittest.main()
