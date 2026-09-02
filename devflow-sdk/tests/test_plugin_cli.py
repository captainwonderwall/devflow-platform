"""Verify devflow_sdk.plugin.cli is importable and runnable as a module."""
import subprocess
import sys


def test_cli_module_is_importable():
    from devflow_sdk.plugin import cli
    assert callable(cli.main)


def test_cli_module_path_matches_homebrew_formula_and_is_runnable():
    import re
    from pathlib import Path
    repo_root = Path(__file__).parents[2]
    formula = (repo_root / "homebrew-devflow" / "Formula" / "devflow.rb").read_text()
    m = re.search(r"python3 -m (devflow_sdk\.\S+)", formula)
    assert m, "Could not find 'python3 -m devflow_sdk.*' in devflow.rb"
    module_path = m.group(1).rstrip('"').rstrip("'")
    result = subprocess.run(
        [sys.executable, "-m", module_path, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"exit {result.returncode}: {result.stderr}"
    assert "devflow-plugin" in result.stdout
