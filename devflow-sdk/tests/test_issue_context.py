import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from devflow_sdk.issue_context import write_issue_context, remove_issue_context, read_issue_context

_ISSUE = {
    "source": "github",
    "id": "42",
    "title": "Add dark mode",
    "body": "Users want dark mode",
    "comments": [],
    "issuetype": "",
    "labels": ["enhancement"],
}


def _git_commondir_result(path):
    r = MagicMock()
    r.returncode = 0
    r.stdout = path + "\n"
    return r


class TestWriteIssueContext(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.worktree_path = self._tmpdir.name
        self.commondir = os.path.join(self._tmpdir.name, ".git")
        os.makedirs(os.path.join(self.commondir, "info"))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write(self, issue=None):
        with patch("subprocess.run", return_value=_git_commondir_result(self.commondir)):
            write_issue_context(self.worktree_path, issue or _ISSUE)

    def test_creates_issue_json_at_worktree_root(self):
        self._write()
        self.assertTrue(os.path.exists(os.path.join(self.worktree_path, ".issue.json")))

    def test_issue_json_contains_full_issue_data(self):
        self._write()
        with open(os.path.join(self.worktree_path, ".issue.json")) as f:
            data = json.load(f)
        self.assertEqual(data, _ISSUE)

    def test_adds_issue_json_to_info_exclude(self):
        self._write()
        exclude_path = os.path.join(self.commondir, "info", "exclude")
        with open(exclude_path) as f:
            content = f.read()
        self.assertIn(".issue.json", content)

    def test_does_not_duplicate_exclude_entry_on_second_call(self):
        self._write()
        self._write()
        exclude_path = os.path.join(self.commondir, "info", "exclude")
        with open(exclude_path) as f:
            content = f.read()
        self.assertEqual(content.count(".issue.json"), 1)

    def test_appends_to_existing_exclude_file(self):
        exclude_path = os.path.join(self.commondir, "info", "exclude")
        with open(exclude_path, "w") as f:
            f.write("*.pyc\n")
        self._write()
        with open(exclude_path) as f:
            lines = f.read().splitlines()
        self.assertIn("*.pyc", lines)
        self.assertIn(".issue.json", lines)

    def test_still_writes_json_when_git_commondir_fails(self):
        failure = MagicMock()
        failure.returncode = 1
        failure.stdout = ""
        with patch("subprocess.run", return_value=failure):
            write_issue_context(self.worktree_path, _ISSUE)
        self.assertTrue(os.path.exists(os.path.join(self.worktree_path, ".issue.json")))


class TestReadIssueContext(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.worktree_path = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_returns_issue_dict_when_file_exists(self):
        issue_path = os.path.join(self.worktree_path, ".issue.json")
        with open(issue_path, "w") as f:
            json.dump(_ISSUE, f)
        self.assertEqual(read_issue_context(self.worktree_path), _ISSUE)

    def test_returns_none_when_file_absent(self):
        self.assertIsNone(read_issue_context(self.worktree_path))

    def test_returns_none_when_file_has_invalid_json(self):
        issue_path = os.path.join(self.worktree_path, ".issue.json")
        with open(issue_path, "w") as f:
            f.write("not json {{{")
        self.assertIsNone(read_issue_context(self.worktree_path))


class TestRemoveIssueContext(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.worktree_path = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_removes_issue_json_when_present(self):
        issue_path = os.path.join(self.worktree_path, ".issue.json")
        with open(issue_path, "w") as f:
            json.dump(_ISSUE, f)
        remove_issue_context(self.worktree_path)
        self.assertFalse(os.path.exists(issue_path))

    def test_does_not_raise_when_file_absent(self):
        remove_issue_context(self.worktree_path)  # must not raise


if __name__ == "__main__":
    unittest.main()
