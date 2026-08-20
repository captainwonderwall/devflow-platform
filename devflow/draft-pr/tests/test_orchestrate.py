#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchestrate import check_existing_pr, run_create_script


class TestCheckExistingPr(unittest.TestCase):
    @patch("orchestrate.subprocess.run")
    def test_returns_url_when_pr_exists(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"url": "https://github.com/org/repo/pull/42"}]',
        )
        url = check_existing_pr("feature/CONS-123")
        self.assertEqual(url, "https://github.com/org/repo/pull/42")

    @patch("orchestrate.subprocess.run")
    def test_returns_none_when_no_pr(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        url = check_existing_pr("feature/CONS-123")
        self.assertIsNone(url)

    @patch("orchestrate.subprocess.run")
    def test_returns_none_when_gh_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        url = check_existing_pr("feature/CONS-123")
        self.assertIsNone(url)

    @patch("orchestrate.subprocess.run")
    def test_returns_none_when_stdout_invalid_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        url = check_existing_pr("feature/CONS-123")
        self.assertIsNone(url)


class TestRunCreateScript(unittest.TestCase):
    @patch("orchestrate.subprocess.run")
    def test_returns_url_on_exact_line(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/org/repo/pull/42\n", stderr=""
        )
        url, error = run_create_script()
        self.assertEqual(url, "https://github.com/org/repo/pull/42")
        self.assertIsNone(error)

    @patch("orchestrate.subprocess.run")
    def test_returns_url_when_prefixed_with_whitespace(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="  Created PR: https://github.com/org/repo/pull/42  \n", stderr=""
        )
        url, error = run_create_script()
        self.assertEqual(url, "https://github.com/org/repo/pull/42")
        self.assertIsNone(error)

    @patch("orchestrate.subprocess.run")
    def test_returns_stdout_as_error_when_no_url_found(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="gh: something unexpected happened", stderr=""
        )
        url, error = run_create_script()
        self.assertIsNone(url)
        self.assertEqual(error, "gh: something unexpected happened")

    @patch("orchestrate.subprocess.run")
    def test_returns_none_error_when_stdout_empty_and_no_url(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        url, error = run_create_script()
        self.assertIsNone(url)
        self.assertIsNone(error)

    @patch("orchestrate.subprocess.run")
    def test_returns_none_error_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        url, error = run_create_script()
        self.assertIsNone(url)
        self.assertIsNone(error)


class TestTmpDir(unittest.TestCase):
    def test_tmp_dir_is_scripts_dir_relative(self):
        import orchestrate
        expected = os.path.join(orchestrate.SCRIPTS_DIR, ".tmp")
        self.assertEqual(orchestrate.TMP_DIR, expected)

    def test_script_path_inside_tmp_dir(self):
        import orchestrate
        self.assertEqual(orchestrate.SCRIPT_PATH, os.path.join(orchestrate.TMP_DIR, "create-pr.sh"))


if __name__ == "__main__":
    unittest.main()
