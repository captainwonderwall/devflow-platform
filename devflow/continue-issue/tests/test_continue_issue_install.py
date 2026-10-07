import os
import subprocess
import tempfile
import unittest
from pathlib import Path


_INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
_SENTINEL = "# >>> continue-issue shell integration >>>"
_END_SENTINEL = "# <<< continue-issue shell integration <<<"


class TestShellIntegrationInstaller(unittest.TestCase):
    def _install(self, home: str, shell: str = "/bin/bash") -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({"HOME": home, "SHELL": shell})
        return subprocess.run(
            ["bash", str(_INSTALLER), "--shell-only"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_new_install_uses_worktree_path_for_switching(self):
        with tempfile.TemporaryDirectory() as home:
            self._install(home)
            function = (Path(home) / ".bashrc").read_text()

        self.assertIn("wt -C", function)
        self.assertIn(".continue-issue-worktree-path", function)
        self.assertIn(
            "rm -f ~/.continue-issue-branch ~/.continue-issue-worktree-path", function
        )
        self.assertNotIn('wt switch "$(cat ~/.continue-issue-branch)"', function)

    def test_upgrades_old_shell_integration(self):
        old_function = (
            f"{_SENTINEL}\n"
            "continue-issue() {\n"
            "    command continue-issue \"$@\" || return\n"
            "    local _rc=0\n"
            "    if [ -f ~/.continue-issue-branch ]; then\n"
            "        wt switch \"$(cat ~/.continue-issue-branch)\" || _rc=$?\n"
            "    fi\n"
            "    rm -f ~/.continue-issue-branch\n"
            "    return $_rc\n"
            "}\n"
            f"{_END_SENTINEL}\n"
        )
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".bashrc").write_text(old_function)
            self._install(home)
            function = (Path(home) / ".bashrc").read_text()

        self.assertIn("wt -C", function)
        self.assertIn(".continue-issue-worktree-path", function)
        self.assertNotIn('wt switch "$(cat ~/.continue-issue-branch)"', function)

    def test_replaces_block_preserves_unrelated_content_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            rc_file = Path(home) / ".bashrc"
            rc_file.write_text(
                "# keep me\n"
                f"{_SENTINEL}\nold function\n{_END_SENTINEL}\n"
                "# >>> finish-issue shell integration >>>\nwt -C finish-context\n"
                "# <<< finish-issue shell integration <<<\n"
                "# >>> start-issue shell integration >>>\nwt -C start-context\n"
                "# <<< start-issue shell integration <<<\n"
            )
            self._install(home)
            self._install(home)
            result = rc_file.read_text()

        self.assertIn("# keep me", result)
        self.assertIn("wt -C finish-context", result)
        self.assertIn("wt -C start-context", result)
        self.assertNotIn("old function", result)
        self.assertEqual(result.count(_SENTINEL), 1)
        self.assertEqual(result.count(_END_SENTINEL), 1)

    def test_appends_to_zshrc_when_block_is_absent(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".zshrc").write_text("# preserve this\n")
            self._install(home, shell="/bin/zsh")
            content = (Path(home) / ".zshrc").read_text()
        self.assertIn("# preserve this", content)
        self.assertIn(_SENTINEL, content)

    def test_switches_from_outside_git_repo_and_cleans_both_markers_on_failure(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as bin_dir:
            self._install(home)
            bin_path = Path(bin_dir)
            continue_command = bin_path / "continue-issue"
            continue_command.write_text("#!/bin/sh\nexit 0\n")
            continue_command.chmod(0o755)
            wt_log = Path(home) / "wt-args"
            wt_command = bin_path / "wt"
            wt_command.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$WT_LOG"\nexit 17\n'
            )
            wt_command.chmod(0o755)

            branch_marker = Path(home) / ".continue-issue-branch"
            path_marker = Path(home) / ".continue-issue-worktree-path"
            branch_marker.write_text("feat/65")
            path_marker.write_text("/repos/worktree with spaces")

            env = os.environ.copy()
            env.update(
                {
                    "HOME": home,
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "WT_LOG": str(wt_log),
                }
            )
            result = subprocess.run(
                ["bash", "-c", 'source "$HOME/.bashrc"; continue-issue'],
                cwd=home,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 17)
            self.assertEqual(
                wt_log.read_text().splitlines(),
                ["-C", "/repos/worktree with spaces", "switch", "feat/65"],
            )
            self.assertFalse(branch_marker.exists())
            self.assertFalse(path_marker.exists())


if __name__ == "__main__":
    unittest.main()
