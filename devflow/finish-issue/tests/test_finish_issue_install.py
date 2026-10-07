import os
import subprocess
import tempfile
import unittest
from pathlib import Path


_INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
_SENTINEL = "# >>> finish-issue shell integration >>>"
_END_SENTINEL = "# <<< finish-issue shell integration <<<"


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

        self.assertIn('wt -C "$_worktree_path" switch "$_switch_to"', function)

    def test_upgrades_shell_integration_without_explicit_worktree_context(self):
        old_function = (
            f"{_SENTINEL}\n"
            "finish-issue() {\n"
            "    command finish-issue --prepare \"$@\" || return\n"
            "    local _rc=0\n"
            "    local _switch_to _remove _worktree_path\n"
            "    _switch_to=\"$(cat ~/.finish-issue-branch 2>/dev/null || true)\"\n"
            "    _remove=\"$(cat ~/.finish-issue-remove 2>/dev/null || true)\"\n"
            "    _worktree_path=\"$(cat ~/.finish-issue-worktree-path 2>/dev/null || true)\"\n"
            "    if [ -n \"$_switch_to\" ]; then\n"
            "        wt switch \"$_switch_to\" || return $?\n"
            "    fi\n"
            "    return $_rc\n"
            "}\n"
            f"{_END_SENTINEL}\n"
        )
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".bashrc").write_text(old_function)
            self._install(home)
            function = (Path(home) / ".bashrc").read_text()

        self.assertIn('wt -C "$_worktree_path" switch "$_switch_to"', function)

    def test_replaces_stale_block_and_preserves_other_integrations(self):
        stale_block = (
            f"{_SENTINEL}\nfinish-issue() {{\n"
            "    wt switch old-branch\n"
            f"{_END_SENTINEL}\n"
        )
        other_integrations = (
            "# >>> start-issue shell integration >>>\nwt -C start-context\n"
            "# <<< start-issue shell integration <<<\n"
            "# >>> continue-issue shell integration >>>\nwt -C continue-context\n"
            "# <<< continue-issue shell integration <<<\n"
        )
        with tempfile.TemporaryDirectory() as home:
            rc_file = Path(home) / ".bashrc"
            rc_file.write_text("# unrelated setting\n" + stale_block + other_integrations)
            self._install(home)
            self._install(home)
            result = rc_file.read_text()

        self.assertIn("# unrelated setting", result)
        self.assertIn("wt -C start-context", result)
        self.assertIn("wt -C continue-context", result)
        self.assertIn('wt -C "$_worktree_path" switch "$_switch_to"', result)
        self.assertNotIn("wt switch old-branch", result)
        self.assertEqual(result.count(_SENTINEL), 1)
        self.assertEqual(result.count(_END_SENTINEL), 1)

    def test_installs_zshrc_when_shell_is_zsh(self):
        with tempfile.TemporaryDirectory() as home:
            self._install(home, shell="/bin/zsh")
            self.assertTrue((Path(home) / ".zshrc").exists())
            self.assertFalse((Path(home) / ".bashrc").exists())

    def test_switches_from_outside_git_repo_using_selected_worktree_context(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as bin_dir:
            self._install(home)
            bin_path = Path(bin_dir)
            finish_command = bin_path / "finish-issue"
            finish_command.write_text("#!/bin/sh\nexit 0\n")
            finish_command.chmod(0o755)
            wt_log = Path(home) / "wt-args"
            wt_command = bin_path / "wt"
            wt_command.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" >> "$WT_LOG"\n'
                'if [ "$1" = "-C" ]; then exit 0; fi\n'
                'if [ "$1" = "switch" ]; then exit 91; fi\n'
                "exit 0\n"
            )
            wt_command.chmod(0o755)
            (Path(home) / ".finish-issue-branch").write_text("main")
            (Path(home) / ".finish-issue-remove").write_text("feat/LSPAY-46539")
            (Path(home) / ".finish-issue-worktree-path").write_text(
                "/repos/worktree with spaces"
            )

            env = os.environ.copy()
            env.update(
                {
                    "HOME": home,
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "WT_LOG": str(wt_log),
                }
            )
            result = subprocess.run(
                ["bash", "-c", 'source "$HOME/.bashrc"; finish-issue LSPAY-46539'],
                cwd=home,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                wt_log.read_text().splitlines(),
                [
                    "-C",
                    "/repos/worktree with spaces",
                    "switch",
                    "main",
                    "remove",
                    "feat/LSPAY-46539",
                ],
            )

    def test_failed_switch_does_not_remove_worktree(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as bin_dir:
            self._install(home)
            bin_path = Path(bin_dir)
            finish_command = bin_path / "finish-issue"
            finish_command.write_text("#!/bin/sh\nexit 0\n")
            finish_command.chmod(0o755)
            wt_log = Path(home) / "wt-args"
            wt_command = bin_path / "wt"
            wt_command.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" >> "$WT_LOG"\n'
                'if [ "$1" = "-C" ]; then exit 17; fi\n'
                'if [ "$1" = "switch" ]; then exit 91; fi\n'
                "exit 0\n"
            )
            wt_command.chmod(0o755)
            (Path(home) / ".finish-issue-branch").write_text("main")
            (Path(home) / ".finish-issue-remove").write_text("feat/LSPAY-46539")
            (Path(home) / ".finish-issue-worktree-path").write_text("/repos/worktree")

            env = os.environ.copy()
            env.update({"HOME": home, "PATH": f"{bin_dir}:{env['PATH']}", "WT_LOG": str(wt_log)})
            result = subprocess.run(
                ["bash", "-c", 'source "$HOME/.bashrc"; finish-issue LSPAY-46539'],
                cwd=home,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 17, result.stderr)
            self.assertEqual(
                wt_log.read_text().splitlines(),
                ["-C", "/repos/worktree", "switch", "main"],
            )
            self.assertTrue((Path(home) / ".finish-issue-remove").exists())


if __name__ == "__main__":
    unittest.main()
