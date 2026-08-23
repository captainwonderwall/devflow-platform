#!/usr/bin/env python3
import os
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
from devflow_sdk.prompts import select, prompt, checkbox
from devflow_sdk.config import load_config, load_tool_config
from config import DraftPrConfig, resolve_plugin

from gather_pr_data import collect
from prepare import validate_state
from prompt_inputs import build_questions
from devflow_sdk.plugin_loader import select_plugin
from devflow_sdk.draft_pr_plugin import DraftPrPlugin
from build_pr_body import write_create_script
from orchestrate import check_existing_pr, run_create_script


PLUGIN_DIR = os.path.join(SCRIPT_DIR, "plugins")
TMP_DIR = os.path.join(SCRIPT_DIR, ".tmp")


def resolve_jira(data, github_issue_arg):
    """Resolve issue reference from data or CLI arg.

    Returns (issue_ref, github_issue).
    """
    jira_ticket = data.get("jira_ticket")
    github_issue = data.get("github_issue") or github_issue_arg

    if jira_ticket:
        jira = select("Confirm Jira ticket", [jira_ticket])
        return jira, github_issue_arg

    if github_issue:
        return f"#{github_issue}", github_issue

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

    plugin = select_plugin(PLUGIN_DIR, DraftPrPlugin, configured_plugin_name)
    if plugin is None:
        print(f"Error: no plugins found in {PLUGIN_DIR}", file=sys.stderr)
        print("Install a plugin into the plugins directory to continue.", file=sys.stderr)
        sys.exit(1)

    # Standard inputs
    jira, github_issue = resolve_jira(data, args.github_issue)
    standard_answers = prompt(build_questions(data))
    jira = standard_answers.get("jira_ticket") or jira   # user may have typed it
    issue_type = standard_answers.get("issue_type") or data.get("issue_type", "Issue")
    checked = checkbox("Is this a customer-visible change?", choices=["Yes", "No"])
    customer_visible = "yes" if "Yes" in (checked or []) else "no"

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
