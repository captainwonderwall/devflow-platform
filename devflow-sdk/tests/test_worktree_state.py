import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from devflow_sdk.worktree_state import (
    WorktreeEntry,
    add_worktree,
    list_tracked_worktrees,
    remove_worktree,
)


class TestAddWorktree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "worktree_state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self):
        return json.loads(self._state_path.read_text())["worktrees"]

    def test_creates_file_when_absent(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        self.assertTrue(self._state_path.exists())
        entries = self._load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0], {"path": "/repos/feat-42", "ticket_id": "42", "source": "github"})

    def test_appends_new_entry(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        add_worktree("/repos/fix-VDP-1", "VDP-1", "jira", state_path=self._state_path)
        self.assertEqual(len(self._load()), 2)

    def test_replaces_entry_with_same_path(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        add_worktree("/repos/feat-42", "99", "jira", state_path=self._state_path)
        entries = self._load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ticket_id"], "99")
        self.assertEqual(entries[0]["source"], "jira")

    def test_recovers_from_corrupt_file(self):
        self._state_path.write_text("not json")
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        entries = self._load()
        self.assertEqual(len(entries), 1)

    def test_prints_warning_on_unwritable_path(self):
        blocker = Path(self._tmp.name) / "blocker"
        blocker.write_text("")                      # a file, not a dir
        unwritable = blocker / "state.json"         # mkdir -> NotADirectoryError
        with patch("sys.stderr") as mock_err:
            add_worktree("/repos/feat-42", "42", "github", state_path=unwritable)
        mock_err.write.assert_called()

    def test_recovers_from_partially_malformed_entries(self):
        # Write state with one valid and one invalid entry
        self._state_path.write_text(json.dumps({"worktrees": [
            {"path": "/repos/valid", "ticket_id": "1", "source": "github"},
            "not_a_dict",
        ]}))
        add_worktree("/repos/new", "2", "github", state_path=self._state_path)
        entries = self._load()
        paths = [e["path"] for e in entries]
        self.assertIn("/repos/valid", paths)
        self.assertIn("/repos/new", paths)
        self.assertNotIn("not_a_dict", paths)


class TestRemoveWorktree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "worktree_state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self):
        return json.loads(self._state_path.read_text())["worktrees"]

    def test_removes_matching_entry(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        add_worktree("/repos/fix-VDP-1", "VDP-1", "jira", state_path=self._state_path)
        remove_worktree("/repos/feat-42", state_path=self._state_path)
        entries = self._load()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "/repos/fix-VDP-1")

    def test_no_op_when_path_not_in_state(self):
        add_worktree("/repos/feat-42", "42", "github", state_path=self._state_path)
        remove_worktree("/repos/nonexistent", state_path=self._state_path)
        self.assertEqual(len(self._load()), 1)

    def test_no_op_when_file_absent(self):
        remove_worktree("/repos/feat-42", state_path=self._state_path)
        # Must not raise and must not create the file
        self.assertFalse(self._state_path.exists())


class TestListWorktrees(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state_path = Path(self._tmp.name) / "worktree_state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_empty_when_file_absent(self):
        result = list_tracked_worktrees(state_path=self._state_path)
        self.assertEqual(result, [])

    def test_returns_all_live_entries(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        add_worktree(str(dir1), "42", "github", state_path=self._state_path)
        result = list_tracked_worktrees(state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], WorktreeEntry(path=str(dir1), ticket_id="42", source="github"))

    def test_purges_stale_entry_and_rewrites_file(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        add_worktree(str(dir1), "42", "github", state_path=self._state_path)
        add_worktree("/nonexistent/wt2", "99", "github", state_path=self._state_path)
        result = list_tracked_worktrees(state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_id, "42")
        raw = json.loads(self._state_path.read_text())["worktrees"]
        self.assertEqual(len(raw), 1)

    def test_skips_purge_when_purge_stale_false(self):
        add_worktree("/nonexistent/wt2", "99", "github", state_path=self._state_path)
        result = list_tracked_worktrees(purge_stale=False, state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_id, "99")

    def test_does_not_rewrite_file_when_no_stale_entries(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        add_worktree(str(dir1), "42", "github", state_path=self._state_path)
        mtime_before = self._state_path.stat().st_mtime
        list_tracked_worktrees(state_path=self._state_path)
        self.assertEqual(self._state_path.stat().st_mtime, mtime_before)

    def test_returns_empty_on_corrupt_file(self):
        self._state_path.write_text("not json")
        result = list_tracked_worktrees(state_path=self._state_path)
        self.assertEqual(result, [])

    def test_list_skips_malformed_entries_but_keeps_valid_ones(self):
        dir1 = Path(self._tmp.name) / "wt1"
        dir1.mkdir()
        self._state_path.write_text(json.dumps({"worktrees": [
            {"path": str(dir1), "ticket_id": "1", "source": "github"},
            {"path": 123, "ticket_id": "bad", "source": "github"},
            "not_a_dict",
        ]}))
        result = list_tracked_worktrees(purge_stale=False, state_path=self._state_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ticket_id, "1")


if __name__ == "__main__":
    unittest.main()
