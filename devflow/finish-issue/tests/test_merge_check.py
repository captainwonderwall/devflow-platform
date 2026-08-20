import sys
import os
import unittest
from unittest.mock import patch, MagicMock

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from merge_check import (
    get_main_branch, is_merged, _is_ancestor, _check_gh_merged_pr,
    _patch_id_matches, _git_patch_id,
)

_WORKTREES = [
    {"branch": "main", "path": "/repos/main", "is_main": True},
    {"branch": "feat/33-add-x", "path": "/repos/33", "is_main": False},
]


class TestGetMainBranch(unittest.TestCase):
    def test_returns_main_branch(self):
        self.assertEqual(get_main_branch(_WORKTREES), "main")

    def test_returns_none_when_missing(self):
        self.assertIsNone(get_main_branch([{"branch": "feat/x", "is_main": False}]))


class TestIsAncestor(unittest.TestCase):
    def test_merged_branch_returns_true(self):
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch("merge_check.subprocess.run", mock_run):
            self.assertTrue(_is_ancestor("/repo", "feat/33-add-x", "origin/main"))
        mock_run.assert_called_once_with(
            ["git", "merge-base", "--is-ancestor", "feat/33-add-x", "origin/main"],
            cwd="/repo", capture_output=True, text=True,
        )

    def test_unmerged_branch_returns_false(self):
        with patch("merge_check.subprocess.run", return_value=MagicMock(returncode=1)):
            self.assertFalse(_is_ancestor("/repo", "feat/33-add-x", "origin/main"))

    def test_unexpected_error_exits(self):
        with patch(
            "merge_check.subprocess.run",
            return_value=MagicMock(returncode=128, stderr="fatal: bad object"),
        ):
            with self.assertRaises(SystemExit):
                _is_ancestor("/repo", "feat/33-add-x", "origin/main")



_GH_CMD = [
    "gh", "pr", "list", "--state", "merged", "--head", "feat/33-add-x",
    "--base", "main", "--json", "number,mergedAt",
]


class TestCheckGhMergedPr(unittest.TestCase):
    def test_merged_pr_found_returns_true(self):
        mock_run = MagicMock(
            return_value=MagicMock(
                returncode=0,
                stdout='[{"number": 33, "mergedAt": "2026-08-01T00:00:00Z"}]',
            )
        )
        with patch("merge_check.subprocess.run", mock_run):
            self.assertTrue(_check_gh_merged_pr("/repo", "feat/33-add-x", "main"))
        mock_run.assert_called_once_with(
            _GH_CMD, cwd="/repo", capture_output=True, text=True,
        )

    def test_no_merged_pr_returns_false(self):
        with patch(
            "merge_check.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="[]"),
        ):
            self.assertFalse(_check_gh_merged_pr("/repo", "feat/33-add-x", "main"))

    def test_gh_not_installed_returns_none(self):
        with patch("merge_check.subprocess.run", side_effect=FileNotFoundError()):
            self.assertIsNone(_check_gh_merged_pr("/repo", "feat/33-add-x", "main"))

    def test_gh_command_failure_returns_none(self):
        with patch(
            "merge_check.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="auth error"),
        ):
            self.assertIsNone(_check_gh_merged_pr("/repo", "feat/33-add-x", "main"))

    def test_gh_invalid_json_returns_none(self):
        with patch(
            "merge_check.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="not json"),
        ):
            self.assertIsNone(_check_gh_merged_pr("/repo", "feat/33-add-x", "main"))

    def test_base_flag_included_for_different_base_branch(self):
        """Verify --base is passed even when checking against a non-main base branch."""
        mock_run = MagicMock(
            return_value=MagicMock(returncode=0, stdout="[]")
        )
        with patch("merge_check.subprocess.run", mock_run):
            _check_gh_merged_pr("/repo", "feat/33-add-x", "release/v2")
        mock_run.assert_called_once_with(
            ["gh", "pr", "list", "--state", "merged", "--head", "feat/33-add-x",
             "--base", "release/v2", "--json", "number,mergedAt"],
            cwd="/repo", capture_output=True, text=True,
        )


def _patch_id_run(merge_base="abc123", branch_diff="branch-diff-text",
                   candidate_commits=None, show_diffs=None, branch_patch_id="patchidA",
                   candidate_patch_ids=None):
    """Build a subprocess.run side_effect for _patch_id_matches scenarios.

    candidate_commits: list of commit SHAs returned by `git log`.
    show_diffs: dict of commit SHA -> diff text returned by `git show`.
    candidate_patch_ids: dict of diff text -> patch-id line returned by `git patch-id`.
    """
    candidate_commits = candidate_commits or []
    show_diffs = show_diffs or {}
    candidate_patch_ids = candidate_patch_ids or {}

    def side_effect(cmd, **kwargs):
        if cmd[:2] == ["git", "merge-base"]:
            return MagicMock(returncode=0, stdout=f"{merge_base}\n")
        if cmd[:2] == ["git", "diff"]:
            return MagicMock(returncode=0, stdout=branch_diff)
        if cmd[:2] == ["git", "log"]:
            stdout = "".join(f"{c}\n" for c in candidate_commits)
            return MagicMock(returncode=0, stdout=stdout)
        if cmd[:2] == ["git", "show"]:
            commit = cmd[2]
            return MagicMock(returncode=0, stdout=show_diffs.get(commit, ""))
        if cmd[:2] == ["git", "patch-id"]:
            diff_text = kwargs.get("input", "")
            if diff_text == branch_diff:
                return MagicMock(returncode=0, stdout=f"{branch_patch_id} {merge_base}\n")
            patch_id = candidate_patch_ids.get(diff_text, "nomatch")
            return MagicMock(returncode=0, stdout=f"{patch_id} deadbeef\n")
        raise AssertionError(f"unexpected command: {cmd}")

    return side_effect


class TestPatchIdMatches(unittest.TestCase):
    def test_matching_commit_returns_true(self):
        side_effect = _patch_id_run(
            candidate_commits=["commit1", "commit2"],
            show_diffs={"commit1": "unrelated-diff", "commit2": "branch-diff-text"},
            branch_patch_id="patchidA",
            candidate_patch_ids={"unrelated-diff": "patchidZ", "branch-diff-text": "patchidA"},
        )
        with patch("merge_check.subprocess.run", side_effect=side_effect):
            self.assertTrue(_patch_id_matches("/repo", "feat/33-add-x", "origin/main"))

    def test_no_matching_commit_returns_false(self):
        side_effect = _patch_id_run(
            candidate_commits=["commit1"],
            show_diffs={"commit1": "unrelated-diff"},
            branch_patch_id="patchidA",
            candidate_patch_ids={"unrelated-diff": "patchidZ"},
        )
        with patch("merge_check.subprocess.run", side_effect=side_effect):
            self.assertFalse(_patch_id_matches("/repo", "feat/33-add-x", "origin/main"))

    def test_no_candidate_commits_returns_false(self):
        side_effect = _patch_id_run(candidate_commits=[])
        with patch("merge_check.subprocess.run", side_effect=side_effect):
            self.assertFalse(_patch_id_matches("/repo", "feat/33-add-x", "origin/main"))

    def test_merge_base_failure_exits(self):
        def side_effect(cmd, **kwargs):
            if cmd[:2] == ["git", "merge-base"]:
                return MagicMock(returncode=1, stdout="", stderr="fatal: no merge base")
            raise AssertionError(f"unexpected command: {cmd}")

        with patch("merge_check.subprocess.run", side_effect=side_effect):
            with self.assertRaises(SystemExit):
                _patch_id_matches("/repo", "feat/33-add-x", "origin/main")

    def test_git_patch_id_failure_exits(self):
        """git patch-id returning non-zero should exit(1), not silently return None."""
        with patch(
            "merge_check.subprocess.run",
            return_value=MagicMock(returncode=128, stdout="", stderr="fatal: broken"),
        ):
            with self.assertRaises(SystemExit):
                _git_patch_id("/repo", "some diff content\n")


class TestIsMerged(unittest.TestCase):
    def test_ancestor_true_short_circuits(self):
        with patch("merge_check.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("merge_check._is_ancestor", return_value=True) as mock_ancestor, \
             patch("merge_check._check_gh_merged_pr") as mock_gh, \
             patch("merge_check._patch_id_matches") as mock_patch_id:
            self.assertTrue(is_merged("/repo", "feat/33-add-x", "main"))
        mock_ancestor.assert_called_once()
        mock_gh.assert_not_called()
        mock_patch_id.assert_not_called()

    def test_gh_true_short_circuits_patch_id(self):
        with patch("merge_check.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("merge_check._is_ancestor", return_value=False) as mock_ancestor, \
             patch("merge_check._check_gh_merged_pr", return_value=True) as mock_gh, \
             patch("merge_check._patch_id_matches") as mock_patch_id:
            self.assertTrue(is_merged("/repo", "feat/33-add-x", "main"))
        mock_ancestor.assert_called_once()
        mock_gh.assert_called_once()
        mock_patch_id.assert_not_called()

    def test_gh_inconclusive_falls_back_to_patch_id(self):
        with patch("merge_check.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("merge_check._is_ancestor", return_value=False), \
             patch("merge_check._check_gh_merged_pr", return_value=None), \
             patch("merge_check._patch_id_matches", return_value=True) as mock_patch_id:
            self.assertTrue(is_merged("/repo", "feat/33-add-x", "main"))
        mock_patch_id.assert_called_once()

    def test_gh_false_falls_back_to_patch_id(self):
        with patch("merge_check.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("merge_check._is_ancestor", return_value=False), \
             patch("merge_check._check_gh_merged_pr", return_value=False), \
             patch("merge_check._patch_id_matches", return_value=True) as mock_patch_id:
            self.assertTrue(is_merged("/repo", "feat/33-add-x", "main"))
        mock_patch_id.assert_called_once()

    def test_all_tiers_false_returns_false(self):
        with patch("merge_check.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("merge_check._is_ancestor", return_value=False), \
             patch("merge_check._check_gh_merged_pr", return_value=False), \
             patch("merge_check._patch_id_matches", return_value=False):
            self.assertFalse(is_merged("/repo", "feat/33-add-x", "main"))

    def test_falls_back_to_local_main_when_fetch_fails(self):
        def side_effect(cmd, **kwargs):
            if cmd[:2] == ["git", "fetch"]:
                return MagicMock(returncode=1)  # fetch fails (offline)
            return MagicMock(returncode=0)

        with patch("merge_check.subprocess.run", side_effect=side_effect), \
             patch("merge_check._is_ancestor", return_value=True) as mock_ancestor:
            result = is_merged("/repo", "feat/33-add-x", "main")

        self.assertTrue(result)
        # target_ref falls back to the plain main_branch, not origin/main
        mock_ancestor.assert_called_once_with("/repo", "feat/33-add-x", "main")


if __name__ == "__main__":
    unittest.main()
