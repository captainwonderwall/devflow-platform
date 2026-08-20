#!/usr/bin/env python3
import sys
import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from importlib import import_module

address_pr = import_module("address-pr")


def _mock_result(returncode=0, stdout=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


class TestGetCurrentSha(unittest.TestCase):
    def test_returns_stripped_sha_on_success(self):
        with patch("subprocess.run",
                    return_value=_mock_result(0, "abc1234\n")):
            self.assertEqual(address_pr.get_current_sha(), "abc1234")

    def test_raises_on_failure(self):
        with patch("subprocess.run", return_value=_mock_result(128, "")):
            with self.assertRaises(RuntimeError):
                address_pr.get_current_sha()


class TestContentHash(unittest.TestCase):
    def test_returns_hash_for_existing_file(self):
        with patch("os.path.isfile", return_value=True), \
             patch("subprocess.run",
                    return_value=_mock_result(0, "deadbeef\n")):
            self.assertEqual(address_pr._content_hash("a.py"), "deadbeef")

    def test_returns_none_for_missing_file(self):
        with patch("os.path.isfile", return_value=False):
            self.assertIsNone(address_pr._content_hash("missing.py"))

    def test_returns_none_when_hash_object_fails(self):
        with patch("os.path.isfile", return_value=True), \
             patch("subprocess.run", return_value=_mock_result(1, "")):
            self.assertIsNone(address_pr._content_hash("a.py"))


class TestGetWorkingTreeStatus(unittest.TestCase):
    def test_parses_porcelain_lines_with_content_hash(self):
        porcelain = " M tracked_modified.py\n?? new_untracked.py\n"
        with patch("subprocess.run",
                    return_value=_mock_result(0, porcelain)), \
             patch.object(address_pr, "_content_hash",
                          side_effect=["hash1", "hash2"]):
            status = address_pr.get_working_tree_status()
        self.assertEqual(status, {
            "tracked_modified.py": (" M", "hash1"),
            "new_untracked.py": ("??", "hash2"),
        })

    def test_handles_renames_keyed_on_new_path(self):
        porcelain = "R  old_name.py -> new_name.py\n"
        with patch("subprocess.run",
                    return_value=_mock_result(0, porcelain)), \
             patch.object(address_pr, "_content_hash", return_value="h"):
            status = address_pr.get_working_tree_status()
        self.assertEqual(status, {"new_name.py": ("R ", "h")})

    def test_empty_status_returns_empty_dict(self):
        with patch("subprocess.run", return_value=_mock_result(0, "")):
            self.assertEqual(address_pr.get_working_tree_status(), {})


class TestFilesTouchedByClaude(unittest.TestCase):
    def test_excludes_unrelated_preexisting_dirty_file(self):
        before = {"unrelated.py": (" M", "hashA")}
        after = {"unrelated.py": (" M", "hashA"), "fixed.py": (" M", "hashB")}
        self.assertEqual(
            address_pr.files_touched_by_claude(before, after), ["fixed.py"]
        )

    def test_detects_further_edit_to_already_dirty_file(self):
        # Same status code both times, but the content hash changed because
        # Claude edited a file that was already dirty before it ran.
        before = {"already_dirty.py": (" M", "hash_before")}
        after = {"already_dirty.py": (" M", "hash_after")}
        self.assertEqual(
            address_pr.files_touched_by_claude(before, after),
            ["already_dirty.py"],
        )

    def test_includes_new_untracked_file(self):
        before = {}
        after = {"new_file.py": ("??", "hash1")}
        self.assertEqual(
            address_pr.files_touched_by_claude(before, after),
            ["new_file.py"],
        )

    def test_no_changes_returns_empty_list(self):
        before = {"a.py": (" M", "hash1")}
        after = {"a.py": (" M", "hash1")}
        self.assertEqual(address_pr.files_touched_by_claude(before, after), [])


class TestHeadAdvancedViaCommit(unittest.TestCase):
    def test_true_when_reflog_says_commit(self):
        with patch("subprocess.run",
                    return_value=_mock_result(0, "commit: address review\n")):
            self.assertTrue(address_pr.head_advanced_via_commit())

    def test_false_when_reflog_says_reset(self):
        with patch("subprocess.run",
                    return_value=_mock_result(0, "reset: moving to HEAD~1\n")):
            self.assertFalse(address_pr.head_advanced_via_commit())

    def test_false_when_reflog_command_fails(self):
        with patch("subprocess.run", return_value=_mock_result(1, "")):
            self.assertFalse(address_pr.head_advanced_via_commit())


class TestCommitChanges(unittest.TestCase):
    def test_commits_and_returns_new_sha_when_staged_changes_exist(self):
        # add -> ok, diff --cached --quiet -> 1 (changes present),
        # commit -> ok, rev-parse HEAD -> new sha
        side_effects = [
            _mock_result(0),      # git add -A
            _mock_result(1),      # git diff --cached --quiet
            _mock_result(0),      # git commit
            _mock_result(0, "newsha1\n"),  # get_current_sha() rev-parse
        ]
        with patch("subprocess.run", side_effect=side_effects) as mock_run:
            sha = address_pr.commit_changes(["alice"])
        self.assertEqual(sha, "newsha1")
        commit_call = mock_run.call_args_list[2]
        self.assertIn("commit", commit_call[0][0])
        add_call = mock_run.call_args_list[0]
        self.assertEqual(add_call[0][0], ["git", "add", "-A"])

    def test_scopes_add_to_given_paths(self):
        side_effects = [
            _mock_result(0),      # git add -- path1 path2
            _mock_result(1),      # git diff --cached --quiet
            _mock_result(0),      # git commit
            _mock_result(0, "newsha1\n"),
        ]
        with patch("subprocess.run", side_effect=side_effects) as mock_run:
            address_pr.commit_changes(["alice"], paths=["path1", "path2"])
        add_call = mock_run.call_args_list[0]
        self.assertEqual(
            add_call[0][0], ["git", "add", "--", "path1", "path2"]
        )

    def test_returns_none_immediately_when_paths_is_empty_list(self):
        with patch("subprocess.run") as mock_run:
            sha = address_pr.commit_changes(["alice"], paths=[])
        self.assertIsNone(sha)
        mock_run.assert_not_called()

    def test_returns_none_when_no_staged_changes(self):
        side_effects = [
            _mock_result(0),   # git add -A
            _mock_result(0),   # git diff --cached --quiet (no diff)
        ]
        with patch("subprocess.run", side_effect=side_effects):
            sha = address_pr.commit_changes(["alice"])
        self.assertIsNone(sha)

    def test_raises_on_diff_error(self):
        side_effects = [
            _mock_result(0),   # git add -A
            _mock_result(2),   # git diff --cached --quiet errors out
        ]
        with patch("subprocess.run", side_effect=side_effects):
            with self.assertRaises(subprocess.CalledProcessError):
                address_pr.commit_changes(["alice"])


class TestSelfCommitDetection(unittest.TestCase):
    """Covers the sha_before/sha_after + working-tree-snapshot branching in
    main(): commit_changes() is always invoked (scoped to Claude's files) to
    pick up any leftover uncommitted changes, even when Claude already made
    a partial commit of its own."""

    def _resolve_sha(self, sha_before, sha_after, claude_files,
                      head_advanced, leftover_sha):
        # head_advanced isn't consumed by this branching (it only affects
        # the warning message in main()), but is accepted here to mirror
        # the call sites and keep test intent readable.
        with patch.object(address_pr, "commit_changes",
                           return_value=leftover_sha) as mock_commit:
            if sha_before != sha_after:
                sha = sha_after
            else:
                sha = None
            result = address_pr.commit_changes(["alice"], paths=claude_files)
            if result is not None:
                sha = result
            return sha, mock_commit

    def test_claude_committed_and_left_no_leftovers(self):
        sha, mock_commit = self._resolve_sha(
            "sha_before", "sha_after", claude_files=[],
            head_advanced=True, leftover_sha=None,
        )
        mock_commit.assert_called_once_with(["alice"], paths=[])
        self.assertEqual(sha, "sha_after")

    def test_claude_committed_but_left_uncommitted_file(self):
        sha, mock_commit = self._resolve_sha(
            "sha_before", "sha_after", claude_files=["leftover.py"],
            head_advanced=True, leftover_sha="final_sha",
        )
        mock_commit.assert_called_once_with(["alice"], paths=["leftover.py"])
        self.assertEqual(sha, "final_sha")

    def test_claude_did_not_commit_but_edited_files(self):
        sha, mock_commit = self._resolve_sha(
            "same_sha", "same_sha", claude_files=["edited.py"],
            head_advanced=False, leftover_sha="committed_sha",
        )
        mock_commit.assert_called_once_with(["alice"], paths=["edited.py"])
        self.assertEqual(sha, "committed_sha")

    def test_no_commit_and_no_files_touched(self):
        sha, mock_commit = self._resolve_sha(
            "same_sha", "same_sha", claude_files=[],
            head_advanced=False, leftover_sha=None,
        )
        mock_commit.assert_called_once_with(["alice"], paths=[])
        self.assertIsNone(sha)


if __name__ == "__main__":
    unittest.main()
