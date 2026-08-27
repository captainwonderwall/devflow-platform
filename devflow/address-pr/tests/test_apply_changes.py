#!/usr/bin/env python3
import contextlib
import io
import sys
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from importlib import import_module

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
apply_changes_mod = import_module("apply_changes")
from fetch_comments import Comment
from devflow_sdk.ai import AiResult
from devflow_sdk.config import DevflowConfig, GlobalConfig


def _mock_result(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _mock_ai_text(result_text, ok=True, needs_interaction=False, session_id="sess-1"):
    return AiResult(result=result_text, session_id=session_id, ok=ok,
                    error="" if ok else result_text, needs_interaction=needs_interaction,
                    total_tokens=100)


def _make_comment(body="some comment"):
    return Comment(
        id="1", kind="pr_comment", author="alice", is_bot=False,
        body=body, file=None, line=None, url="http://example.com",
        thread_node_id=None,
    )


class TestExtractEdits(unittest.TestCase):
    def test_returns_none_when_no_edits_tag(self):
        self.assertIsNone(apply_changes_mod.extract_edits("just some text"))

    def test_returns_empty_list_when_edits_tag_empty(self):
        self.assertEqual(apply_changes_mod.extract_edits("<edits></edits>"), [])

    def test_returns_empty_list_when_edits_tag_whitespace_only(self):
        self.assertEqual(
            apply_changes_mod.extract_edits("<edits>\n  \n</edits>"), [])

    def test_uses_last_edits_block_when_claude_self_corrects(self):
        # Claude occasionally emits a stray empty <edits></edits> before
        # catching itself mid-response and emitting the real one right
        # after (observed on --resume'd sessions). The final block is the
        # one that should win, not the first (empty) one.
        output = (
            "<edits></edits>\n\n"
            "Wait — I need to produce the edits, not apply them.\n\n"
            "<edits>\n"
            '<file path="a.py">\n'
            "<old>\nfoo()\n</old>\n"
            "<new>\nfoo()\nbar()\n</new>\n"
            "</file>\n"
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].path, "a.py")
        self.assertEqual(edits[0].replacements, [("foo()", "foo()\nbar()")])

    def test_parses_single_file_single_replacement(self):
        output = (
            "<edits>\n"
            '<file path="a.py">\n'
            "<old>\nfoo()\n</old>\n"
            "<new>\nfoo()\nbar()\n</new>\n"
            "</file>\n"
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        self.assertEqual(len(edits), 1)
        e = edits[0]
        self.assertEqual(e.path, "a.py")
        self.assertFalse(e.create)
        self.assertEqual(e.replacements, [("foo()", "foo()\nbar()")])

    def test_preserves_indentation_in_old_and_new(self):
        output = (
            "<edits>\n"
            '<file path="a.py">\n'
            "<old>\n    def foo():\n        pass\n</old>\n"
            "<new>\n    def foo():\n        return 1\n</new>\n"
            "</file>\n"
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        old, new = edits[0].replacements[0]
        self.assertEqual(old, "    def foo():\n        pass")
        self.assertEqual(new, "    def foo():\n        return 1")

    def test_parses_multiple_replacements_in_one_file_in_order(self):
        output = (
            "<edits>\n"
            '<file path="a.py">\n'
            "<old>\none\n</old>\n<new>\nONE\n</new>\n"
            "<old>\ntwo\n</old>\n<new>\nTWO\n</new>\n"
            "</file>\n"
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        self.assertEqual(
            edits[0].replacements, [("one", "ONE"), ("two", "TWO")])

    def test_parses_multiple_files_in_order(self):
        output = (
            "<edits>\n"
            '<file path="a.py">\n<old>\nx\n</old>\n<new>\ny\n</new>\n</file>\n'
            '<file path="b.py">\n<old>\np\n</old>\n<new>\nq\n</new>\n</file>\n'
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        self.assertEqual([e.path for e in edits], ["a.py", "b.py"])

    def test_parses_create_file_with_content(self):
        output = (
            "<edits>\n"
            '<file path="new_mod.py" create="true">\n'
            "<content>\nprint('hi')\n</content>\n"
            "</file>\n"
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        self.assertEqual(len(edits), 1)
        e = edits[0]
        self.assertEqual(e.path, "new_mod.py")
        self.assertTrue(e.create)
        self.assertEqual(e.content, "print('hi')")
        self.assertEqual(e.replacements, [])

    def test_create_file_without_content_block_has_none_content(self):
        # Regression: a create="true" file with no <content> block must
        # NOT silently default to an empty string (which would let
        # apply_edits() truncate an existing file to zero bytes). None
        # signals "malformed" so apply_edits() can fail closed.
        output = (
            "<edits>\n"
            '<file path="new_mod.py" create="true">\n'
            "</file>\n"
            "</edits>"
        )
        edits = apply_changes_mod.extract_edits(output)
        self.assertEqual(len(edits), 1)
        self.assertIsNone(edits[0].content)


class TestApplyEdits(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._prev_cwd = os.getcwd()
        os.chdir(self.tmpdir.name)
        self.addCleanup(os.chdir, self._prev_cwd)

    def _write(self, path, content):
        with open(path, "w") as f:
            f.write(content)

    def test_applies_single_replacement(self):
        self._write("a.py", "def foo():\n    pass\n")
        edits = [apply_changes_mod.FileEdit(
            path="a.py", create=False, content=None,
            replacements=[("    pass", "    return 1")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok)
        self.assertIsNone(err)
        with open("a.py") as f:
            self.assertEqual(f.read(), "def foo():\n    return 1\n")

    def test_applies_multiple_replacements_in_order(self):
        self._write("a.py", "one\ntwo\n")
        edits = [apply_changes_mod.FileEdit(
            path="a.py", create=False, content=None,
            replacements=[("one", "ONE"), ("two", "TWO")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok)
        with open("a.py") as f:
            self.assertEqual(f.read(), "ONE\nTWO\n")

    def test_fails_when_anchor_not_found(self):
        self._write("a.py", "def foo():\n    pass\n")
        edits = [apply_changes_mod.FileEdit(
            path="a.py", create=False, content=None,
            replacements=[("does not exist", "new")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("a.py", err)
        self.assertIn("not found", err.lower())
        # File must be left untouched.
        with open("a.py") as f:
            self.assertEqual(f.read(), "def foo():\n    pass\n")

    def test_fails_when_anchor_ambiguous(self):
        self._write("a.py", "pass\npass\n")
        edits = [apply_changes_mod.FileEdit(
            path="a.py", create=False, content=None,
            replacements=[("pass", "return 1")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("a.py", err)
        with open("a.py") as f:
            self.assertEqual(f.read(), "pass\npass\n")

    def test_no_files_written_when_one_file_fails(self):
        # Two files in the edit set: first would succeed, second fails.
        # Neither should be written so a retry starts from a clean slate.
        self._write("a.py", "foo\n")
        self._write("b.py", "bar\n")
        edits = [
            apply_changes_mod.FileEdit(
                path="a.py", create=False, content=None,
                replacements=[("foo", "FOO")]),
            apply_changes_mod.FileEdit(
                path="b.py", create=False, content=None,
                replacements=[("missing", "BAR")]),
        ]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        with open("a.py") as f:
            self.assertEqual(f.read(), "foo\n")
        with open("b.py") as f:
            self.assertEqual(f.read(), "bar\n")

    def test_creates_new_file(self):
        edits = [apply_changes_mod.FileEdit(
            path="new_mod.py", create=True, content="print('hi')",
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok)
        with open("new_mod.py") as f:
            self.assertEqual(f.read(), "print('hi')")

    def test_creates_new_file_in_new_subdirectory(self):
        edits = [apply_changes_mod.FileEdit(
            path="sub/dir/new_mod.py", create=True, content="x = 1",
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok)
        with open("sub/dir/new_mod.py") as f:
            self.assertEqual(f.read(), "x = 1")

    def test_creates_new_file_with_explicitly_empty_content(self):
        # An explicit, intentional empty file (content="") must still be
        # allowed — only a missing <content> block (content=None) is an
        # error.
        edits = [apply_changes_mod.FileEdit(
            path="empty.py", create=True, content="", replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok)
        with open("empty.py") as f:
            self.assertEqual(f.read(), "")

    def test_fails_when_create_file_missing_content(self):
        # Regression: a create=True FileEdit with content=None (i.e. no
        # <content> block was present in Claude's output) must fail
        # closed instead of silently truncating/creating an empty file,
        # since that could destroy an existing file's data.
        self._write("existing.py", "important data\n")
        edits = [apply_changes_mod.FileEdit(
            path="existing.py", create=True, content=None,
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("existing.py", err)
        self.assertIn("content", err.lower())
        with open("existing.py") as f:
            self.assertEqual(f.read(), "important data\n")

    def test_fails_when_file_to_edit_missing(self):
        edits = [apply_changes_mod.FileEdit(
            path="missing.py", create=False, content=None,
            replacements=[("a", "b")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("missing.py", err)

    def test_rejects_absolute_path_for_edit(self):
        edits = [apply_changes_mod.FileEdit(
            path="/etc/passwd", create=False, content=None,
            replacements=[("root", "hacked")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("/etc/passwd", err)
        self.assertIn("outside", err.lower())

    def test_rejects_parent_traversal_path_for_edit(self):
        self._write("a.py", "safe\n")
        edits = [apply_changes_mod.FileEdit(
            path="../a.py", create=False, content=None,
            replacements=[("safe", "unsafe")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("../a.py", err)
        self.assertIn("outside", err.lower())

    def test_rejects_absolute_path_for_create(self):
        edits = [apply_changes_mod.FileEdit(
            path="/tmp/evil.py", create=True, content="x = 1",
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("/tmp/evil.py", err)
        self.assertIn("outside", err.lower())
        self.assertFalse(os.path.exists("/tmp/evil.py"))

    def test_rejects_parent_traversal_path_for_create(self):
        edits = [apply_changes_mod.FileEdit(
            path="../escaped.py", create=True, content="x = 1",
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("outside", err.lower())
        self.assertFalse(os.path.exists(
            os.path.join(os.path.dirname(self.tmpdir.name), "escaped.py")))

    def test_allows_nested_relative_path_within_repo(self):
        edits = [apply_changes_mod.FileEdit(
            path="sub/./new_mod.py", create=True, content="x = 1",
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok)
        with open("sub/new_mod.py") as f:
            self.assertEqual(f.read(), "x = 1")


class TestApplyEditsRepoRootDetection(unittest.TestCase):
    """apply_edits() must validate paths against the actual git repo root,
    not just the current working directory, since address-pr can be run
    from any subdirectory of the repo (git status/paths are always
    repo-root-relative regardless of cwd)."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._prev_cwd = os.getcwd()
        self.addCleanup(os.chdir, self._prev_cwd)

    def _git(self, *args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                        capture_output=True)

    def test_accepts_path_escaping_cwd_but_within_real_repo_root(self):
        # Regression: previously repo_root was just os.getcwd(), so a
        # legitimate repo-relative edit that walks up out of the current
        # subdirectory (but stays inside the real repo) was wrongly
        # rejected as "outside the working tree".
        repo = os.path.realpath(self.tmpdir.name)
        self._git("init", "-q", cwd=repo)
        subdir = os.path.join(repo, "sub")
        os.makedirs(subdir)
        root_file = os.path.join(repo, "root_file.py")
        with open(root_file, "w") as f:
            f.write("safe\n")

        os.chdir(subdir)
        edits = [apply_changes_mod.FileEdit(
            path="../root_file.py", create=False, content=None,
            replacements=[("safe", "unsafe")])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertTrue(ok, err)
        with open(root_file) as f:
            self.assertEqual(f.read(), "unsafe\n")

    def test_rejects_symlink_that_resolves_outside_repo(self):
        # abspath()/commonpath() alone don't resolve symlinks, so a
        # symlink inside the working tree pointing outside the repo could
        # otherwise be used to bypass the traversal check.
        repo = os.path.realpath(self.tmpdir.name)
        self._git("init", "-q", cwd=repo)
        outside = tempfile.mkdtemp()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", outside]))
        os.symlink(outside, os.path.join(repo, "escape_link"))

        os.chdir(repo)
        edits = [apply_changes_mod.FileEdit(
            path="escape_link/evil.py", create=True, content="x = 1",
            replacements=[])]
        ok, err = apply_changes_mod.apply_edits(edits)
        self.assertFalse(ok)
        self.assertIn("outside", err.lower())
        self.assertFalse(os.path.exists(os.path.join(outside, "evil.py")))


class TestBuildApplyPrompt(unittest.TestCase):
    def test_prompt_requests_edits_tags(self):
        prompt = apply_changes_mod.build_apply_prompt(
            "My PR", "desc", [_make_comment("fix the bug")])
        self.assertIn("<edits>", prompt)
        self.assertIn("</edits>", prompt)
        self.assertIn("<old>", prompt)
        self.assertIn("<new>", prompt)

    def test_prompt_forbids_prose_outside_tags(self):
        prompt = apply_changes_mod.build_apply_prompt(
            "My PR", "desc", [_make_comment()])
        self.assertIn("nothing outside", prompt.lower())

    def test_prompt_requires_verbatim_unique_anchors(self):
        prompt = apply_changes_mod.build_apply_prompt(
            "My PR", "desc", [_make_comment()])
        self.assertIn("verbatim", prompt.lower())
        self.assertIn("exactly once", prompt.lower())

    def test_prompt_documents_create_attribute(self):
        prompt = apply_changes_mod.build_apply_prompt(
            "My PR", "desc", [_make_comment()])
        self.assertIn('create="true"', prompt)

    def test_prompt_forbids_writing_files_directly(self):
        prompt = apply_changes_mod.build_apply_prompt(
            "My PR", "desc", [_make_comment()])
        self.assertIn("do not write any files directly", prompt.lower())


class TestApplyChangesNormalPath(unittest.TestCase):
    def _claude_result(self, edits_content='<file path="f.py">\n<old>\nx\n</old>\n<new>\ny\n</new>\n</file>'):
        return _mock_ai_text(f"<edits>\n{edits_content}\n</edits>")

    def test_returns_true_on_success(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=self._claude_result()):
            with patch("apply_changes.apply_edits", return_value=(True, None)):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = apply_changes_mod.apply_changes(
                        "Title", "Description", [_make_comment()])
        self.assertTrue(result)

    def test_returns_false_on_nonzero_exit_without_prompt(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("boom", ok=False)):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = apply_changes_mod.apply_changes(
                    "Title", "Description", [_make_comment()])
        self.assertFalse(result)

    def test_resume_flag_added_when_session_id_provided(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=self._claude_result()) as mock_ai:
            with patch("apply_changes.apply_edits", return_value=(True, None)):
                with contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()):
                    apply_changes_mod.apply_changes(
                        "Title", "Description", [_make_comment()],
                        session_id="sess-123")
        call_kwargs = mock_ai.call_args_list[0][1]
        self.assertEqual(call_kwargs.get("session_id"), "sess-123")

    def test_no_resume_flag_when_session_id_is_none(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=self._claude_result()) as mock_ai:
            with patch("apply_changes.apply_edits", return_value=(True, None)):
                with contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()):
                    apply_changes_mod.apply_changes(
                        "Title", "Description", [_make_comment()],
                        session_id=None)
        call_kwargs = mock_ai.call_args_list[0][1]
        self.assertIsNone(call_kwargs.get("session_id"))


class TestApplyChangesWithEdits(unittest.TestCase):
    def _claude_result(self, edits_content='<file path="f.py">\n<old>\nx\n</old>\n<new>\ny\n</new>\n</file>'):
        return _mock_ai_text(f"<edits>\n{edits_content}\n</edits>")

    def test_returns_false_when_no_edits_tag(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("I made some changes")):
            with contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                result = apply_changes_mod.apply_changes(
                    "Title", "Desc", [_make_comment()])
        self.assertFalse(result)

    def test_returns_true_and_noops_when_edits_tags_empty(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("<edits></edits>")) as mock_run:
            with contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                result = apply_changes_mod.apply_changes(
                    "Title", "Desc", [_make_comment()])
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 1)

    def test_returns_false_when_claude_exits_nonzero(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("error", ok=False)):
            with contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                result = apply_changes_mod.apply_changes(
                    "Title", "Desc", [_make_comment()])
        self.assertFalse(result)

    def test_debug_forwarded_to_run_ai_prompt(self):
        edits_content = '<file path="f.py">\n<old>\nx\n</old>\n<new>\ny\n</new>\n</file>'
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text(f"<edits>{edits_content}</edits>")) as mock_run:
            with patch("apply_changes.apply_edits", return_value=(True, None)):
                with contextlib.redirect_stdout(io.StringIO()):
                    apply_changes_mod.apply_changes(
                        "Title", "Desc", [_make_comment()], debug=True)
        _, kwargs = mock_run.call_args
        self.assertTrue(kwargs.get("debug"))

    def test_debug_false_by_default_forwarded_to_run_ai_prompt(self):
        edits_content = '<file path="f.py">\n<old>\nx\n</old>\n<new>\ny\n</new>\n</file>'
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text(f"<edits>{edits_content}</edits>")) as mock_run:
            with patch("apply_changes.apply_edits", return_value=(True, None)):
                with contextlib.redirect_stdout(io.StringIO()):
                    apply_changes_mod.apply_changes(
                        "Title", "Desc", [_make_comment()])
        _, kwargs = mock_run.call_args
        self.assertFalse(kwargs.get("debug"))


class TestApplyChangesRetry(unittest.TestCase):
    def _claude_result(self, edits_content='<file path="f.py">\n<old>\nx\n</old>\n<new>\ny\n</new>\n</file>',
                        session_id="sess-abc"):
        result_text = f"<edits>\n{edits_content}\n</edits>"
        return _mock_ai_text(result_text, session_id=session_id)

    def test_retries_and_succeeds_on_second_attempt(self):
        first = self._claude_result()
        second = self._claude_result()
        with patch("apply_changes.run_ai_prompt",
                    side_effect=[first, second]) as mock_run:
            with patch("apply_changes.apply_edits",
                        side_effect=[(False, "anchor not found in f.py"),
                                     (True, None)]):
                with contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()):
                    result = apply_changes_mod.apply_changes(
                        "Title", "Desc", [_make_comment()])
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)
        # The retry call must resume the same Claude session and mention
        # the specific failure so Claude can self-correct.
        second_call_kwargs = mock_run.call_args_list[1][1]
        self.assertEqual(second_call_kwargs.get("session_id"), "sess-abc")
        second_call_prompt = mock_run.call_args_list[1][0][0]
        self.assertIn("anchor not found in f.py", second_call_prompt)

    def test_gives_up_after_max_attempts(self):
        first = self._claude_result()
        second = self._claude_result()
        with patch("apply_changes.run_ai_prompt",
                    side_effect=[first, second]) as mock_run:
            with patch("apply_changes.apply_edits",
                        return_value=(False, "anchor not found in f.py")):
                with contextlib.redirect_stdout(io.StringIO()), \
                     contextlib.redirect_stderr(io.StringIO()):
                    result = apply_changes_mod.apply_changes(
                        "Title", "Desc", [_make_comment()])
        self.assertFalse(result)
        self.assertEqual(mock_run.call_count, 2)


class TestApplyChangesPermissionMenu(unittest.TestCase):
    def _claude_config(self):
        return DevflowConfig(global_config=GlobalConfig(ai_provider="claude"))

    def test_resumes_interactively_and_returns_success(self):
        interactive_ok = _mock_result(0)
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("", needs_interaction=True)):
            with patch("apply_changes.load_config", return_value=self._claude_config()):
                with patch("apply_changes.subprocess.run",
                        return_value=interactive_ok) as mock_run:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        result = apply_changes_mod.apply_changes(
                            "Title", "Description", [_make_comment()])
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 1)
        first_call_args, first_call_kwargs = mock_run.call_args_list[0]
        self.assertEqual(
            first_call_args[0],
            ["claude", "--permission-mode", "bypassPermissions",
             "--continue"],
        )
        self.assertNotIn("capture_output", first_call_kwargs)
        self.assertNotIn("-p", first_call_args[0])

    def test_resumes_with_session_id_when_provided(self):
        interactive_ok = _mock_result(0)
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("", needs_interaction=True)):
            with patch("apply_changes.load_config", return_value=self._claude_config()):
                with patch("apply_changes.subprocess.run",
                        return_value=interactive_ok) as mock_run:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        result = apply_changes_mod.apply_changes(
                            "Title", "Description", [_make_comment()],
                            session_id="sess-123")
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 1)
        first_call_args, first_call_kwargs = mock_run.call_args_list[0]
        self.assertEqual(
            first_call_args[0],
            ["claude", "--permission-mode", "bypassPermissions",
             "--resume", "sess-123"],
        )
        self.assertNotIn("--continue", first_call_args[0])
        self.assertNotIn("capture_output", first_call_kwargs)

    def test_returns_false_when_interactive_run_fails(self):
        interactive_fail = _mock_result(1)
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("", needs_interaction=True)):
            with patch("apply_changes.subprocess.run",
                        return_value=interactive_fail):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = apply_changes_mod.apply_changes(
                        "Title", "Description", [_make_comment()])
        self.assertFalse(result)

    def test_returns_false_when_subprocess_raises_oserror(self):
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("", needs_interaction=True)):
            with patch("apply_changes.subprocess.run",
                        side_effect=OSError("claude not found")):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = apply_changes_mod.apply_changes(
                        "Title", "Description", [_make_comment()])
        self.assertFalse(result)

    def test_detects_prompt_in_stderr_too(self):
        interactive_ok = _mock_result(0)
        with patch("apply_changes.run_ai_prompt",
                   return_value=_mock_ai_text("", needs_interaction=True)):
            with patch("apply_changes.subprocess.run",
                        return_value=interactive_ok):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = apply_changes_mod.apply_changes(
                        "Title", "Description", [_make_comment()])
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
