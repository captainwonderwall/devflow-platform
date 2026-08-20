import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))

from ide_config import _copy_folder, _rewrite_paths, copy_ide_config, IDE_CONFIG_FOLDERS, detect_ides, prompt_and_open_ide, prompt_and_open_ai_agent


class TestIdeConfigFoldersConstant(unittest.TestCase):
    def test_contains_idea_and_vscode(self):
        self.assertEqual(IDE_CONFIG_FOLDERS, (".idea", ".vscode"))


class TestCopyFolder(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.main_root = os.path.join(self.tmpdir, "main")
        self.worktree = os.path.join(self.tmpdir, "worktree")
        os.makedirs(self.main_root)
        os.makedirs(self.worktree)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_copies_folder_when_source_exists(self):
        src = os.path.join(self.main_root, ".idea")
        os.makedirs(src)
        with open(os.path.join(src, "misc.xml"), "w") as f:
            f.write("<root/>")
        dest = os.path.join(self.worktree, ".idea")

        result = _copy_folder(src, dest)

        self.assertTrue(result)
        self.assertTrue(os.path.isfile(os.path.join(dest, "misc.xml")))

    def test_skips_when_source_missing(self):
        src = os.path.join(self.main_root, ".vscode")
        dest = os.path.join(self.worktree, ".vscode")

        result = _copy_folder(src, dest)

        self.assertFalse(result)
        self.assertFalse(os.path.exists(dest))

    def test_skips_when_dest_already_exists(self):
        src = os.path.join(self.main_root, ".idea")
        os.makedirs(src)
        with open(os.path.join(src, "misc.xml"), "w") as f:
            f.write("<root/>")
        dest = os.path.join(self.worktree, ".idea")
        os.makedirs(dest)
        with open(os.path.join(dest, "existing.txt"), "w") as f:
            f.write("pre-existing")

        result = _copy_folder(src, dest)

        self.assertFalse(result)
        self.assertTrue(os.path.isfile(os.path.join(dest, "existing.txt")))
        self.assertFalse(os.path.isfile(os.path.join(dest, "misc.xml")))

    def test_cleans_up_partial_copy_on_failure(self):
        src = os.path.join(self.main_root, ".idea")
        os.makedirs(src)
        with open(os.path.join(src, "misc.xml"), "w") as f:
            f.write("<root/>")
        dest = os.path.join(self.worktree, ".idea")

        # Simulate what a failed copytree might leave behind: a partially
        # created dest directory with a stray file in it.
        def fake_copytree(_src, _dest):
            os.makedirs(_dest)
            with open(os.path.join(_dest, "partial.xml"), "w") as f:
                f.write("partial")
            raise OSError("disk full")

        with patch("ide_config.shutil.copytree", side_effect=fake_copytree):
            with self.assertRaises(OSError):
                _copy_folder(src, dest)

        self.assertFalse(os.path.exists(dest))


class TestRewritePaths(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmpdir, ".idea")
        os.makedirs(self.dest)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_replaces_old_path_with_new_path_in_text_file(self):
        old_root = "/Users/dev/work/ai-utils"
        new_root = "/Users/dev/work/ai-utils.feat-my-branch"
        fpath = os.path.join(self.dest, "misc.xml")
        with open(fpath, "w") as f:
            f.write(f'<project><jdk path="{old_root}/venv" /></project>')

        _rewrite_paths(self.dest, old_root, new_root)

        with open(fpath) as f:
            content = f.read()
        self.assertIn(new_root, content)

    def test_leaves_file_unchanged_when_old_path_not_present(self):
        fpath = os.path.join(self.dest, "modules.xml")
        original = '<modules><module fileurl="file://$PROJECT_DIR$/app.iml" /></modules>'
        with open(fpath, "w") as f:
            f.write(original)

        _rewrite_paths(self.dest, "/Users/dev/work/ai-utils", "/Users/dev/work/ai-utils.new")

        with open(fpath) as f:
            self.assertEqual(f.read(), original)

    def test_skips_binary_file_without_raising(self):
        fpath = os.path.join(self.dest, "icon.bin")
        with open(fpath, "wb") as f:
            f.write(b"\xff\xfe\x00\x01binarydata\x80\x81")

        _rewrite_paths(self.dest, "/Users/dev/work/ai-utils", "/Users/dev/work/ai-utils.new")

        with open(fpath, "rb") as f:
            self.assertEqual(f.read(), b"\xff\xfe\x00\x01binarydata\x80\x81")

    def test_rewrites_nested_files(self):
        old_root = "/Users/dev/work/ai-utils"
        new_root = "/Users/dev/work/ai-utils.new"
        nested_dir = os.path.join(self.dest, "runConfigurations")
        os.makedirs(nested_dir)
        fpath = os.path.join(nested_dir, "Run.xml")
        with open(fpath, "w") as f:
            f.write(f'<configuration workingDir="{old_root}" />')

        _rewrite_paths(self.dest, old_root, new_root)

        with open(fpath) as f:
            self.assertIn(new_root, f.read())

    def test_does_not_mangle_sibling_path_with_shared_prefix(self):
        # old_root and new_root are NOT prefixes of each other, but a
        # sibling path exists that has old_root as a strict prefix.
        old_root = "/Users/dev/work/main-repo"
        new_root = "/Users/dev/work/other-worktree"

        exact_fpath = os.path.join(self.dest, "exact.xml")
        with open(exact_fpath, "w") as f:
            f.write(f'<jdk path="{old_root}" />')

        sibling_fpath = os.path.join(self.dest, "sibling.xml")
        sibling_original = f'<jdk path="{old_root}-legacy" />'
        with open(sibling_fpath, "w") as f:
            f.write(sibling_original)

        _rewrite_paths(self.dest, old_root, new_root)

        with open(exact_fpath) as f:
            exact_content = f.read()
        self.assertIn(new_root, exact_content)
        self.assertNotIn(old_root, exact_content)

        with open(sibling_fpath) as f:
            sibling_content = f.read()
        self.assertEqual(sibling_content, sibling_original)


class TestCopyIdeConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.main_root = os.path.join(self.tmpdir, "main")
        self.worktree = os.path.join(self.tmpdir, "worktree")
        os.makedirs(self.main_root)
        os.makedirs(self.worktree)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_idea(self, root, text):
        idea = os.path.join(root, ".idea")
        os.makedirs(idea)
        with open(os.path.join(idea, "misc.xml"), "w") as f:
            f.write(text)
        return idea

    def test_copies_and_rewrites_idea_when_vscode_absent(self):
        self._make_idea(self.main_root, f'<jdk path="{self.main_root}/venv" />')

        copy_ide_config(self.main_root, self.worktree)

        dest_file = os.path.join(self.worktree, ".idea", "misc.xml")
        self.assertTrue(os.path.isfile(dest_file))
        with open(dest_file) as f:
            content = f.read()
        self.assertIn(self.worktree, content)
        self.assertFalse(os.path.exists(os.path.join(self.worktree, ".vscode")))

    def test_copies_both_when_both_present(self):
        self._make_idea(self.main_root, "<root/>")
        vscode = os.path.join(self.main_root, ".vscode")
        os.makedirs(vscode)
        with open(os.path.join(vscode, "settings.json"), "w") as f:
            f.write("{}")

        copy_ide_config(self.main_root, self.worktree)

        self.assertTrue(os.path.isdir(os.path.join(self.worktree, ".idea")))
        self.assertTrue(os.path.isdir(os.path.join(self.worktree, ".vscode")))

    def test_neither_present_does_nothing(self):
        copy_ide_config(self.main_root, self.worktree)

        self.assertFalse(os.path.exists(os.path.join(self.worktree, ".idea")))
        self.assertFalse(os.path.exists(os.path.join(self.worktree, ".vscode")))

    def test_copy_failure_is_non_fatal_and_warns(self):
        self._make_idea(self.main_root, "<root/>")
        with patch("ide_config._copy_folder", side_effect=OSError("disk full")):
            with patch("sys.stderr") as mock_stderr:
                copy_ide_config(self.main_root, self.worktree)
            mock_stderr.write.assert_called()

    def test_prints_confirmation_for_each_copied_folder(self):
        self._make_idea(self.main_root, "<root/>")
        with patch("builtins.print") as mock_print:
            copy_ide_config(self.main_root, self.worktree)
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn(".idea config", printed)


class TestDetectIdes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_empty_when_no_ide_config_present(self):
        result = detect_ides(self.tmpdir)
        self.assertEqual(result, [])

    def test_detects_vscode_when_vscode_folder_exists(self):
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        result = detect_ides(self.tmpdir)
        self.assertEqual(result, [("VS Code", "code")])

    def test_detects_intellij_when_idea_folder_exists(self):
        os.makedirs(os.path.join(self.tmpdir, ".idea"))
        result = detect_ides(self.tmpdir)
        self.assertEqual(result, [("IntelliJ IDEA", "idea")])

    def test_detects_both_when_both_folders_exist(self):
        os.makedirs(os.path.join(self.tmpdir, ".idea"))
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        result = detect_ides(self.tmpdir)
        self.assertEqual(len(result), 2)
        self.assertIn(("IntelliJ IDEA", "idea"), result)
        self.assertIn(("VS Code", "code"), result)


class TestPromptAndOpenIde(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_does_nothing_when_no_ides_detected(self):
        with patch("ide_config.subprocess.run") as mock_run, \
             patch("ide_config.select") as mock_select:
            prompt_and_open_ide(self.tmpdir)
        mock_run.assert_not_called()
        mock_select.assert_not_called()

    def test_launches_vscode_when_user_selects_vscode(self):
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        with patch("ide_config.subprocess.run") as mock_run, \
             patch("ide_config.select", return_value="code"):
            prompt_and_open_ide(self.tmpdir)
        mock_run.assert_called_once_with(["code", "."], cwd=self.tmpdir)

    def test_launches_intellij_when_user_selects_intellij(self):
        os.makedirs(os.path.join(self.tmpdir, ".idea"))
        with patch("ide_config.subprocess.run") as mock_run, \
             patch("ide_config.select", return_value="idea"):
            prompt_and_open_ide(self.tmpdir)
        mock_run.assert_called_once_with(["idea", "."], cwd=self.tmpdir)

    def test_skips_when_user_selects_skip(self):
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        with patch("ide_config.subprocess.run") as mock_run, \
             patch("ide_config.select", return_value=None):
            prompt_and_open_ide(self.tmpdir)
        mock_run.assert_not_called()

    def test_skips_when_user_cancels_with_ctrl_c(self):
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        with patch("ide_config.subprocess.run") as mock_run, \
             patch("ide_config.select", return_value=None):
            prompt_and_open_ide(self.tmpdir)
        mock_run.assert_not_called()

    def test_warns_and_continues_when_ide_command_not_on_path(self):
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        with patch("ide_config.subprocess.run", side_effect=FileNotFoundError), \
             patch("ide_config.select", return_value="code"), \
             patch("ide_config.sys.stderr") as mock_stderr:
            prompt_and_open_ide(self.tmpdir)  # must not raise
        mock_stderr.write.assert_called()

    def test_launches_intellij_when_both_detected_and_intellij_chosen(self):
        os.makedirs(os.path.join(self.tmpdir, ".idea"))
        os.makedirs(os.path.join(self.tmpdir, ".vscode"))
        with patch("ide_config.subprocess.run") as mock_run, \
             patch("ide_config.select", return_value="idea"):
            prompt_and_open_ide(self.tmpdir)
        mock_run.assert_called_once_with(["idea", "."], cwd=self.tmpdir)


class TestPromptAndOpenAiAgent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_launches_agent_when_user_selects_open(self):
        with patch("ide_config.select", return_value="open"), \
             patch("ide_config.launch_interactive_session") as mock_launch:
            prompt_and_open_ai_agent(self.tmpdir)
        mock_launch.assert_called_once_with(
            "Brainstorm a solution for the issue described in .issue.json",
            cwd=self.tmpdir,
        )

    def test_skips_when_user_selects_none(self):
        with patch("ide_config.select", return_value=None), \
             patch("ide_config.launch_interactive_session") as mock_launch:
            prompt_and_open_ai_agent(self.tmpdir)
        mock_launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
