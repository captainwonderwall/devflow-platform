import os
import subprocess
import tempfile
import unittest
from pathlib import Path


_INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
_SENTINEL = "# >>> start-issue shell integration >>>"
_END_SENTINEL = "# <<< start-issue shell integration <<<"


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
        self.assertIn(".start-issue-worktree-path", function)
        self.assertIn(
            "rm -f ~/.start-issue-branch ~/.start-issue-worktree-path", function
        )
        self.assertNotIn('wt switch "$(cat ~/.start-issue-branch)"', function)

    def test_manual_instructions_use_worktree_path(self):
        with tempfile.TemporaryDirectory() as home:
            result = self._install(home, shell="/bin/fish")

        self.assertIn("wt -C", result.stdout)
        self.assertIn(".start-issue-worktree-path", result.stdout)
        self.assertIn(
            "rm -f ~/.start-issue-branch ~/.start-issue-worktree-path", result.stdout
        )

    def test_upgrades_old_shell_integration(self):
        old_function = (
            f"{_SENTINEL}\n"
            "start-issue() {\n"
            "    command start-issue \"$@\" || return\n"
            "    local _rc=0\n"
            "    if [ -f ~/.start-issue-branch ]; then\n"
            "        wt switch \"$(cat ~/.start-issue-branch)\" || _rc=$?\n"
            "    fi\n"
            "    rm -f ~/.start-issue-branch\n"
            "    return $_rc\n"
            "}\n"
            f"{_END_SENTINEL}\n"
        )
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".bashrc").write_text(old_function)
            self._install(home)
            function = (Path(home) / ".bashrc").read_text()

        self.assertIn("wt -C", function)
        self.assertIn(".start-issue-worktree-path", function)
        self.assertNotIn('wt switch "$(cat ~/.start-issue-branch)"', function)

    def test_switches_from_outside_git_repo_and_cleans_both_markers_on_failure(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as bin_dir:
            self._install(home)
            bin_path = Path(bin_dir)
            start_command = bin_path / "start-issue"
            start_command.write_text("#!/bin/sh\nexit 0\n")
            start_command.chmod(0o755)
            wt_log = Path(home) / "wt-args"
            wt_command = bin_path / "wt"
            wt_command.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$WT_LOG"\nexit 17\n'
            )
            wt_command.chmod(0o755)

            branch_marker = Path(home) / ".start-issue-branch"
            path_marker = Path(home) / ".start-issue-worktree-path"
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
                ["bash", "-c", 'source "$HOME/.bashrc"; start-issue'],
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
