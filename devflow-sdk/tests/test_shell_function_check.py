import os
import tempfile
from unittest.mock import patch

from devflow_sdk.shell_function_check import check_shell_function

SENTINEL = "# >>> my-script shell integration >>>"
HINT = "Run: install.sh"
REQUIRED = "command my-script --prepare"


class TestCheckShellFunction:
    def test_exits_when_sentinel_missing_from_rc_file(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text("export PATH=$HOME/bin:$PATH\n")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            try:
                check_shell_function(SENTINEL, HINT)
                assert False, "expected SystemExit"
            except SystemExit as e:
                assert e.code != 0

    def test_succeeds_when_sentinel_present_and_no_required_content(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text(f"export PATH=$HOME/bin:$PATH\n{SENTINEL}\n")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            check_shell_function(SENTINEL, HINT)  # must not raise

    def test_succeeds_when_sentinel_and_required_content_both_present(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text(f"{SENTINEL}\n{REQUIRED}\n")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            check_shell_function(SENTINEL, HINT, required_content=REQUIRED)  # must not raise

    def test_exits_when_sentinel_present_but_required_content_missing(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text(f"{SENTINEL}\ncommand my-script\n")  # old version, no --prepare
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            try:
                check_shell_function(SENTINEL, HINT, required_content=REQUIRED)
                assert False, "expected SystemExit"
            except SystemExit as e:
                assert e.code != 0

    def test_succeeds_when_all_list_fragments_present(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text(f"{SENTINEL}\n{REQUIRED}\nextra-flag\n")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            check_shell_function(SENTINEL, HINT, required_content=[REQUIRED, "extra-flag"])

    def test_exits_when_one_list_fragment_missing(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text(f"{SENTINEL}\n{REQUIRED}\n")  # "extra-flag" absent
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            try:
                check_shell_function(SENTINEL, HINT, required_content=[REQUIRED, "extra-flag"])
                assert False, "expected SystemExit"
            except SystemExit as e:
                assert e.code != 0

    def test_exits_when_rc_file_does_not_exist(self, tmp_path):
        nonexistent = str(tmp_path / "no_such_file")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=nonexistent):
            try:
                check_shell_function(SENTINEL, HINT)
                assert False, "expected SystemExit"
            except SystemExit as e:
                assert e.code != 0

    def test_uses_zshrc_for_zsh_shell(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text(SENTINEL)
        seen_paths = []

        def fake_expanduser(path):
            seen_paths.append(path)
            return str(rc) if ".zshrc" in path else str(tmp_path / "other")

        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", side_effect=fake_expanduser):
            check_shell_function(SENTINEL, HINT)
        assert any(".zshrc" in p for p in seen_paths)

    def test_uses_bashrc_for_bash_shell(self, tmp_path):
        rc = tmp_path / ".bashrc"
        rc.write_text(SENTINEL)
        seen_paths = []

        def fake_expanduser(path):
            seen_paths.append(path)
            return str(rc) if ".bashrc" in path else str(tmp_path / "other")

        with patch.dict(os.environ, {"SHELL": "/bin/bash"}), \
             patch("os.path.expanduser", side_effect=fake_expanduser):
            check_shell_function(SENTINEL, HINT)
        assert any(".bashrc" in p for p in seen_paths)

    def test_exits_for_unrecognized_shell(self, tmp_path):
        with patch.dict(os.environ, {"SHELL": "/bin/fish"}):
            try:
                check_shell_function(SENTINEL, HINT)
                assert False, "expected SystemExit"
            except SystemExit as e:
                assert e.code != 0

    def test_prints_install_hint_on_missing_sentinel(self, tmp_path, capsys):
        rc = tmp_path / ".zshrc"
        rc.write_text("no sentinel here\n")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            try:
                check_shell_function(SENTINEL, HINT)
            except SystemExit:
                pass
        captured = capsys.readouterr()
        assert HINT in captured.err

    def test_prints_install_hint_when_required_content_missing(self, tmp_path, capsys):
        rc = tmp_path / ".zshrc"
        rc.write_text(f"{SENTINEL}\nold content\n")
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}), \
             patch("os.path.expanduser", return_value=str(rc)):
            try:
                check_shell_function(SENTINEL, HINT, required_content=REQUIRED)
            except SystemExit:
                pass
        captured = capsys.readouterr()
        assert HINT in captured.err
