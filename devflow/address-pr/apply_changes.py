#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from typing import List, NamedTuple, Optional, Tuple
from fetch_comments import Comment

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)
from devflow_sdk.core.ai import configured_provider_display_name, run_ai_prompt
from devflow_sdk.core.ai.providers import get_provider
from devflow_sdk.core.config import load_config


class FileEdit(NamedTuple):
    path: str
    create: bool
    content: Optional[str]
    replacements: List[Tuple[str, str]]


def _strip_wrapper_newlines(raw: str) -> str:
    # <old>/<new>/<content> blocks are written as
    #   <tag>\n  actual content\n</tag>
    # The newline right after the opening tag and right before the closing
    # tag are just wrapper padding, not part of the file content, so strip
    # exactly one of each. A general .strip() would also eat meaningful
    # leading indentation or trailing blank lines that are part of the
    # anchor/replacement text.
    if raw.startswith("\n"):
        raw = raw[1:]
    if raw.endswith("\n"):
        raw = raw[:-1]
    return raw


_FILE_RE = re.compile(
    r'<file\s+path="([^"]+)"(\s+create="true")?\s*>(.*?)</file>', re.DOTALL)
_OLD_NEW_RE = re.compile(r'<old>(.*?)</old>\s*<new>(.*?)</new>', re.DOTALL)
_CONTENT_RE = re.compile(r'<content>(.*?)</content>', re.DOTALL)


def extract_edits(output: str) -> Optional[List[FileEdit]]:
    # Claude occasionally self-corrects mid-response (e.g. resumed sessions
    # sometimes emit a stray empty "<edits></edits>" before catching itself
    # and emitting the real one right after). Use the LAST <edits> block
    # rather than the first, since that reflects Claude's final answer —
    # otherwise a premature empty block would be mistaken for "no changes
    # needed" and silently discard the real edits that follow it.
    matches = list(re.finditer(r'<edits>(.*?)</edits>', output, re.DOTALL))
    if not matches:
        return None
    match = matches[-1]

    edits = []
    for file_path, create_attr, body in _FILE_RE.findall(match.group(1)):
        is_create = bool(create_attr)
        if is_create:
            content_match = _CONTENT_RE.search(body)
            content = (_strip_wrapper_newlines(content_match.group(1))
                       if content_match else None)
            edits.append(FileEdit(path=file_path, create=True,
                                  content=content, replacements=[]))
        else:
            replacements = [
                (_strip_wrapper_newlines(old), _strip_wrapper_newlines(new))
                for old, new in _OLD_NEW_RE.findall(body)
            ]
            edits.append(FileEdit(path=file_path, create=False,
                                  content=None, replacements=replacements))
    return edits


def _get_repo_root() -> str:
    """Return the git repository root (symlinks resolved), falling back
    to the current working directory if we're not inside a git repo or
    `git` isn't available (e.g. under test). Using the real repo root
    instead of os.getcwd() means edits are validated correctly even when
    address-pr is invoked from a subdirectory of the repo — git status
    (and thus every path address-pr deals with) is always repo-root
    relative regardless of cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return os.path.realpath(result.stdout.strip())
    except OSError:
        pass
    return os.path.realpath(os.getcwd())


def apply_edits(edits: List[FileEdit]) -> Tuple[bool, Optional[str]]:
    """Apply anchored search/replace edits and file creations.

    Validates every edit up front and only writes to disk if the whole
    batch succeeds, so a failure (missing/ambiguous anchor) never leaves
    the working tree partially modified — a clean slate for a retry.
    """
    repo_root = _get_repo_root()
    to_write = []  # list of (path, new_content)

    for edit in edits:
        # Resolve relative to cwd (where files are actually read/written)
        # but use realpath so symlinks can't be used to bypass the repo
        # boundary check below.
        resolved = os.path.realpath(os.path.join(os.getcwd(), edit.path))
        # Reject absolute paths and any ../ traversal (directly or via a
        # symlink) that would escape the repo root — model-generated
        # paths are untrusted input, and writing outside the working
        # tree must never be possible.
        if os.path.commonpath([repo_root, resolved]) != repo_root:
            return False, (
                f"Refusing to write outside the repo: {edit.path!r} "
                "resolves outside the working tree")

        if edit.create:
            if edit.content is None:
                return False, (
                    f"Missing <content> block for new file {edit.path!r} "
                    "— refusing to write an empty/truncated file")
            to_write.append((edit.path, edit.content))
            continue

        try:
            with open(edit.path, "r") as f:
                text = f.read()
        except OSError as e:
            return False, f"Could not read {edit.path}: {e}"

        for old, new in edit.replacements:
            count = text.count(old)
            if count == 0:
                snippet = old if len(old) <= 80 else old[:80] + "..."
                return False, (
                    f"Anchor text not found in {edit.path}: {snippet!r}")
            if count > 1:
                snippet = old if len(old) <= 80 else old[:80] + "..."
                return False, (
                    f"Anchor text ambiguous ({count} matches) in "
                    f"{edit.path}: {snippet!r}")
            text = text.replace(old, new, 1)

        to_write.append((edit.path, text))

    for path, content in to_write:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    return True, None


MAX_APPLY_ATTEMPTS = 2


def build_apply_prompt(pr_title: str, pr_description: str,
                       comments: List[Comment]) -> str:
    lines = [
        f"You are addressing PR review comments for: {pr_title}",
        "",
        "PR description:",
        pr_description.strip() if pr_description.strip() else "(none)",
        "",
        "Review comments to address:",
    ]
    for c in comments:
        loc = f" at {c.file}:{c.line}" if c.file else ""
        lines.append(f"\n@{c.author}{loc}:")
        lines.append(f'"{c.body}"')
        if c.verdict and c.reason:
            lines.append(f"(AI assessment: {c.verdict} — {c.reason})")
    lines.extend([
        "",
        "Instructions:",
        "- Read the relevant files to understand what changes are needed.",
        "- Output the required changes as anchored search/replace edits, "
        "wrapped in <edits></edits> tags, using this exact format:",
        '  <file path="relative/path.py">',
        "  <old>",
        "  ...exact existing text to replace (verbatim, including "
        "indentation)...",
        "  </old>",
        "  <new>",
        "  ...replacement text...",
        "  </new>",
        "  </file>",
        "- A <file> block may contain multiple <old>/<new> pairs, applied "
        "in the order given.",
        "- Each <old> block MUST be copied verbatim from the file's actual "
        "current content (exact whitespace and indentation) and MUST "
        "appear exactly once in the file — do not paraphrase, reformat, "
        "or reconstruct it from memory.",
        "- To create a brand-new file, use "
        '<file path="relative/path.py" create="true"> with a single '
        "<content>...</content> block containing the full file contents "
        "(no <old>/<new> needed).",
        "- Put nothing outside the tags — no prose, no explanation, no "
        "markdown fences.",
        "- If no changes are needed, output empty <edits></edits> tags.",
        "- Do not write any files directly.",
    ])
    return "\n".join(lines)


def _build_retry_prompt(error: str) -> str:
    return (
        "Your previous <edits> block could not be applied for this reason:\n"
        f"{error}\n\n"
        "Re-read ALL the files involved in ALL the review comments above, "
        "then output a COMPLETE corrected <edits> block that addresses "
        "every comment — not just the one that failed. Make sure every "
        "<old> block is copied verbatim from the file's actual current "
        "content (matching whitespace and indentation exactly) and appears "
        "exactly once."
    )


def apply_changes(pr_title: str, pr_description: str,
                  comments: List[Comment],
                  session_id: Optional[str] = None,
                  debug: bool = False) -> bool:
    prompt = build_apply_prompt(pr_title, pr_description, comments)
    current_session_id = session_id
    last_error = None

    for attempt in range(1, MAX_APPLY_ATTEMPTS + 1):
        attempt_prompt = prompt if attempt == 1 else _build_retry_prompt(last_error)
        ai_result = run_ai_prompt(
            attempt_prompt,
            tier="capable",
            result_type="text",
            trust_level="full",
            session_id=current_session_id,
            debug=debug,
        )

        if ai_result.needs_interaction:
            print(f"{configured_provider_display_name()} needs write permission to modify files "
                  "(bypass permissions may be disabled by an org policy).")
            print("Resuming interactively — answer the approval prompt when "
                  "it appears.\n")
            try:
                config = load_config()
                provider = get_provider(config.global_config)
                resume_cmd = provider.build_interactive_resume_command(current_session_id)
                interactive_proc = subprocess.run(resume_cmd)
                return interactive_proc.returncode == 0
            except OSError as e:
                print(
                    f"Error: Could not run {configured_provider_display_name()}: {e}",
                    file=sys.stderr,
                )
                return False
            except KeyboardInterrupt:
                print("\nCancelled.", file=sys.stderr)
                return False

        if not ai_result.ok:
            if ai_result.error:
                print(ai_result.error, end="", file=sys.stderr)
            return False

        current_session_id = ai_result.session_id or current_session_id
        result_text = ai_result.result

        edits = extract_edits(result_text)
        if edits is None:
            print(
                f"{configured_provider_display_name()} did not produce any edits.",
                file=sys.stderr,
            )
            return False

        if not edits:
            return True

        ok, error = apply_edits(edits)
        if ok:
            return True

        last_error = error
        print(f"Attempt {attempt} failed to apply edits: {error}",
              file=sys.stderr)

    print(f"ERROR: could not apply edits after {MAX_APPLY_ATTEMPTS} "
          f"attempts: {last_error}", file=sys.stderr)
    return False
