#!/usr/bin/env python3
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
VENDOR_DIR = os.path.join(REPO_ROOT, "vendor")
sys.path.insert(0, SCRIPT_DIR)
import glob as _glob
for _whl in sorted(_glob.glob(os.path.join(VENDOR_DIR, "*.whl"))):
    sys.path.insert(0, _whl)

from devflow_sdk.ai import run_ai_prompt
from devflow_sdk.prompts import select, prompt
from devflow_sdk.config import load_config, load_tool_config
from config import DraftPrConfig, resolve_plugin

from gather_pr_data import collect
from prepare import validate_state
from prompt_inputs import build_questions
from plugin_loader import discover
from build_pr_body import write_create_script
from orchestrate import check_existing_pr, run_create_script


PLUGIN_DIR = os.path.join(SCRIPT_DIR, "plugins")
TMP_DIR = os.path.join(SCRIPT_DIR, ".tmp")

_JIRA_RE = re.compile(r'\b([A-Z]+-[0-9]+)\b')


def detect_issue_refs(branch):
    """Return list of JIRA keys found in a branch name."""
    if not branch:
        return []
    return _JIRA_RE.findall(branch)


def resolve_jira(data, github_issue_arg):
    """Resolve Jira ticket from branch/data or github issue.

    Returns (jira_key, github_issue_arg).
    """
    branch = data.get("branch", "")
    refs = detect_issue_refs(branch)
    jira_ticket = data.get("jira_ticket")

    candidates = []
    if jira_ticket:
        candidates.append(jira_ticket)
    for r in refs:
        if r not in candidates:
            candidates.append(r)

    if candidates:
        if len(candidates) == 1:
            jira = select("Confirm Jira ticket", candidates)
        else:
            jira = select("Select Jira ticket", candidates)
        return jira, github_issue_arg

    if github_issue_arg:
        return f"#{github_issue_arg}", github_issue_arg

    return None, github_issue_arg



def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-issue", default=None)
    args, _ = parser.parse_known_args()

    data = collect()
    validate_state(data)
    existing_url = check_existing_pr(data.get("branch", ""))
    if existing_url:
        print(f"PR already exists: {existing_url}")
        sys.exit(0)

    devflow_cfg = load_config()
    draft_pr_cfg = load_tool_config(devflow_cfg, "draft-pr", DraftPrConfig)
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        cwd_rel = os.path.relpath(os.getcwd(), git_root)
    except subprocess.CalledProcessError:
        cwd_rel = os.getcwd()  # fallback: not in a git repo
    configured_plugin_name = resolve_plugin(draft_pr_cfg, cwd_rel)

    plugins = discover(PLUGIN_DIR)
    if not plugins:
        print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
        print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
        sys.exit(1)

    if configured_plugin_name:
        plugin_names = [p.name or type(p).__name__ for p in plugins]
        if configured_plugin_name in plugin_names:
            plugin = plugins[plugin_names.index(configured_plugin_name)]
        else:
            print(
                f"Warning: configured plugin '{configured_plugin_name}' not found. "
                f"Available: {', '.join(plugin_names)}",
                file=sys.stderr,
            )
            plugin = plugins[0] if len(plugins) == 1 else plugins[plugin_names.index(
                select("Select format", choices=plugin_names)
            )]
    elif len(plugins) == 1:
        plugin = plugins[0]
    else:
        plugin_names = [p.name or type(p).__name__ for p in plugins]
        chosen_name = select("Select format", choices=plugin_names)
        plugin = plugins[plugin_names.index(chosen_name)]

    # Standard inputs
    jira, github_issue = resolve_jira(data, args.github_issue)
    standard_answers = prompt(build_questions(data))
    jira = standard_answers.get("jira_ticket") or jira   # user may have typed it
    issue_type = standard_answers.get("issue_type") or data.get("issue_type", "Issue")
    customer_visible = standard_answers.get("customer_visible", "no")

    user_inputs = {
        "jira_ticket": jira,
        "github_issue": github_issue,
        "issue_type": issue_type,
        "customer_visible": customer_visible,
    }

    # Plugin-specific inputs
    extra_questions = plugin.get_questions(data)
    if extra_questions:
        extra_answers = prompt(extra_questions)
        user_inputs.update(extra_answers)

    prompt_str = plugin.build_prompt(data, user_inputs)
    ai_result = run_ai_prompt(prompt_str, tier="capable", result_type="json")
    if not ai_result.ok:
        print(f"AI error: {ai_result.error}", file=sys.stderr)
        sys.exit(1)

    body_str = plugin.build_body(ai_result.result, user_inputs)
    title = ai_result.result.get("title", "") if isinstance(ai_result.result, dict) else ""

    os.makedirs(TMP_DIR, exist_ok=True)
    body_path = os.path.join(TMP_DIR, "pr-body.md")
    script_path = os.path.join(TMP_DIR, "create-pr.sh")

    with open(body_path, "w") as f:
        f.write(body_str)

    write_create_script(title, body_path, script_path)
    url, error = run_create_script(script_path)
    if url:
        print(f"\nPR created: {url}")
    elif error:
        print(f"\nPR creation failed: {error}", file=sys.stderr)
        print(f"Run manually: bash {script_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
