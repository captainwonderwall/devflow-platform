import importlib.util
import os
import sys
import pytest
from unittest.mock import MagicMock, call, patch

_HERE = os.path.dirname(__file__)
_TOOL_DIR = os.path.join(_HERE, "..")

_spec = importlib.util.spec_from_file_location(
    "diagram", os.path.join(_TOOL_DIR, "diagram.py")
)
diagram = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diagram)
sys.modules["diagram"] = diagram


# ── parse_args ────────────────────────────────────────────────────────────────

def test_default_format_is_png():
    args = diagram.parse_args([])
    assert args.format == "png"


def test_default_theme_is_default():
    args = diagram.parse_args([])
    assert args.theme == "default"


def test_output_defaults_to_none():
    args = diagram.parse_args([])
    assert args.output is None


def test_format_flag_accepted():
    assert diagram.parse_args(["--format", "svg"]).format == "svg"
    assert diagram.parse_args(["--format", "pdf"]).format == "pdf"


def test_theme_flag_accepted():
    assert diagram.parse_args(["--theme", "forest"]).theme == "forest"


def test_invalid_format_exits():
    with pytest.raises(SystemExit):
        diagram.parse_args(["--format", "gif"])


def test_invalid_theme_exits():
    with pytest.raises(SystemExit):
        diagram.parse_args(["--theme", "neon"])


# ── _ensure_docker ────────────────────────────────────────────────────────────

def test_ensure_docker_exits_when_not_found():
    with patch("diagram.subprocess.run", return_value=MagicMock(returncode=1)):
        with pytest.raises(SystemExit, match="docker"):
            diagram._ensure_docker()


def test_ensure_docker_passes_when_found():
    with patch("diagram.subprocess.run", return_value=MagicMock(returncode=0)):
        diagram._ensure_docker()  # must not raise


# ── _ensure_image ─────────────────────────────────────────────────────────────

def test_ensure_image_pulls_when_missing(capsys):
    inspect_fail = MagicMock(returncode=1)
    pull_ok = MagicMock(returncode=0)
    with patch("diagram.subprocess.run", side_effect=[inspect_fail, pull_ok]) as mock_run:
        diagram._ensure_image()
    calls = mock_run.call_args_list
    assert "pull" in calls[1][0][0]


def test_ensure_image_skips_pull_when_present():
    with patch("diagram.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        diagram._ensure_image()
    assert mock_run.call_count == 1


# ── _render ───────────────────────────────────────────────────────────────────

def test_render_returns_stdout_bytes():
    ok = MagicMock(returncode=0, stdout=b"\x89PNG", stderr=b"")
    with patch("diagram.subprocess.run", return_value=ok):
        result = diagram._render(b"graph TD; A-->B", "png", "default")
    assert result == b"\x89PNG"


def test_render_includes_format_flag():
    ok = MagicMock(returncode=0, stdout=b"<svg/>", stderr=b"")
    with patch("diagram.subprocess.run", return_value=ok) as mock_run:
        diagram._render(b"graph TD; A-->B", "svg", "default")
    cmd = mock_run.call_args[0][0]
    assert "-e" in cmd
    assert "svg" in cmd


def test_render_includes_theme_flag_when_non_default():
    ok = MagicMock(returncode=0, stdout=b"\x89PNG", stderr=b"")
    with patch("diagram.subprocess.run", return_value=ok) as mock_run:
        diagram._render(b"graph TD; A-->B", "png", "forest")
    cmd = mock_run.call_args[0][0]
    assert "-t" in cmd
    assert "forest" in cmd


def test_render_omits_theme_flag_for_default():
    ok = MagicMock(returncode=0, stdout=b"\x89PNG", stderr=b"")
    with patch("diagram.subprocess.run", return_value=ok) as mock_run:
        diagram._render(b"graph TD; A-->B", "png", "default")
    cmd = mock_run.call_args[0][0]
    assert "-t" not in cmd


def test_render_exits_on_nonzero():
    fail = MagicMock(returncode=1, stderr=b"error")
    with patch("diagram.subprocess.run", return_value=fail):
        with pytest.raises(SystemExit):
            diagram._render(b"graph TD; A-->B", "png", "default")


# ── main ──────────────────────────────────────────────────────────────────────

def test_main_exits_on_empty_stdin():
    mock_stdin_buffer = MagicMock()
    mock_stdin_buffer.read.return_value = b"   \n  "
    with patch("diagram.sys.argv", ["diagram"]):
        with patch("diagram.sys.stdin", MagicMock(buffer=mock_stdin_buffer)):
            with patch("diagram._ensure_docker"):
                with patch("diagram._ensure_image"):
                    with pytest.raises(SystemExit, match="no Mermaid source"):
                        diagram.main()


def test_main_writes_to_stdout_by_default():
    png_bytes = b"\x89PNG"
    mock_stdin_buffer = MagicMock()
    mock_stdin_buffer.read.return_value = b"graph TD; A-->B"
    mock_stdout_buffer = MagicMock()
    with patch("diagram.sys.argv", ["diagram"]):
        with patch("diagram.sys.stdin", MagicMock(buffer=mock_stdin_buffer)):
            with patch("diagram.sys.stdout", MagicMock(buffer=mock_stdout_buffer)):
                with patch("diagram._ensure_docker"):
                    with patch("diagram._ensure_image"):
                        with patch("diagram._render", return_value=png_bytes):
                            diagram.main()
    mock_stdout_buffer.write.assert_called_once_with(png_bytes)


def test_main_writes_to_output_file_when_specified(tmp_path):
    out = tmp_path / "diagram.png"
    png_bytes = b"\x89PNG"
    mock_stdin_buffer = MagicMock()
    mock_stdin_buffer.read.return_value = b"graph TD; A-->B"
    with patch("diagram.sys.stdin", MagicMock(buffer=mock_stdin_buffer)):
        with patch("diagram._ensure_docker"):
            with patch("diagram._ensure_image"):
                with patch("diagram._render", return_value=png_bytes):
                    with patch("diagram.sys.argv", ["diagram", "--output", str(out)]):
                        diagram.main()
    assert out.read_bytes() == png_bytes
