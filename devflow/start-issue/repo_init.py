import os
import re
import subprocess
import sys

from devflow_sdk.core.ai import run_ai_prompt
from devflow_sdk.core.prompts import confirm

WT_CONFIG = ".config/wt.toml"

_CODE_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)\n?```\s*$", re.DOTALL)


def _strip_code_fence(text):
    """Strip a surrounding markdown code fence (e.g. ```toml ... ```) if present."""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()

_CLAUDE_PROMPT_TEMPLATE = """\
Analyze this repository and output the minimal shell commands needed to make a \
fresh git worktree build-ready (dependencies installed, compiled if needed). \
Do NOT include dev server start commands or test commands.

Output ONLY a TOML snippet with no other text, in this exact format:
[pre-start]
install = "<command>"
build = "<command>"

Rules:
- Maven (pom.xml present): use `mvn install -DskipTests`
- npm (package.json present): `npm ci` to install; add `npm run build` only if \
a "build" script exists in package.json
- Omit lines that are not needed
- Use only these key names: install, build, compile

Repository files:
{files}
"""


def has_wt_config(repo_root):
    return os.path.exists(os.path.join(repo_root, WT_CONFIG))


def _collect_repo_files(repo_root):
    snippets = []
    for fname in ["pom.xml", "package.json", "Makefile", "build.gradle"]:
        path = os.path.join(repo_root, fname)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    content = f.read(4000)
                snippets.append(f"=== {fname} ===\n{content}")
            except OSError:
                pass
    return "\n\n".join(snippets) if snippets else "(no recognized build files found)"


def detect_and_write_config(repo_root):
    if has_wt_config(repo_root):
        print(f"Found existing {WT_CONFIG} — skipping repo init.")
        return

    print("No .config/wt.toml found. Detecting repo type with Claude...")
    prompt = _CLAUDE_PROMPT_TEMPLATE.format(files=_collect_repo_files(repo_root))

    ai_result = run_ai_prompt(
        prompt,
        tier="fast",
        result_type="text",
        stateless=True,
        cwd=repo_root,
    )

    if not ai_result.ok:
        print(
            f"WARNING: Claude failed to detect repo type. "
            f"Add [pre-start] hooks to {WT_CONFIG} manually.\n{ai_result.error}",
            file=sys.stderr,
        )
        return

    toml_content = _strip_code_fence(ai_result.result)

    if "[pre-start]" not in toml_content:
        print(
            f"WARNING: Claude output did not contain valid [pre-start] TOML. "
            f"Skipping repo init.",
            file=sys.stderr,
        )
        return

    config_path = os.path.join(repo_root, WT_CONFIG)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    print(f"\nGenerated {WT_CONFIG}:\n")
    print(toml_content)

    with open(config_path, "w") as f:
        f.write(toml_content + "\n")

    if confirm("Commit this file?"):
        try:
            subprocess.run(["git", "add", WT_CONFIG], cwd=repo_root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "chore: add worktrunk project config", "--", WT_CONFIG],
                cwd=repo_root,
                check=True,
            )
            print(f"Committed {WT_CONFIG}.")
        except subprocess.CalledProcessError as e:
            print(
                f"WARNING: could not commit {WT_CONFIG}: {e}\n"
                f"Wrote it (not committed — add and commit it when ready).",
                file=sys.stderr,
            )
    else:
        print(f"Wrote {WT_CONFIG} (not committed — add and commit it when ready).")
