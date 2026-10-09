#!/usr/bin/env python3
import atexit
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

from devflow_sdk.core.ai import run_ai_prompt
from devflow_sdk.core.prompts import select, prompt
from devflow_sdk.core.config import load_config, load_tool_config
from devflow_sdk.core.ui import status, success, error, info
from devflow_sdk.core.summary import summary
from devflow_sdk.plugin import DraftPrPlugin, select_plugin
from devflow_sdk.core.config.wizard.tools.draft_pr import DraftPrConfig, resolve_plugin

from gather_pr_data import collect
from prepare import validate_state
from prompt_inputs import build_questions
from build_pr_body import write_create_script
from orchestrate import check_existing_pr, run_create_script


TMP_DIR = os.path.join(SCRIPT_DIR, ".tmp")


def resolve_jira(data, github_issue_arg):
    """Resolve issue reference from data or CLI arg.

    Returns (issue_ref, github_issue).
    """
    jira_ticket = data.get("jira_ticket")
    github_issue = data.get("github_issue") or github_issue_arg

    if jira_ticket:
        jira = select("Confirm Jira ticket", [jira_ticket], single=True)
        return jira, github_issue_arg

    if github_issue:
        return f"#{github_issue}", github_issue

    return None, github_issue_arg



def main():
    atexit.register(summary.print_summary)
    summary.start_rate_fetch()

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-issue", default=None)
    args, _ = parser.parse_known_args()

    data = collect()
    validate_state(data)
    existing_url = check_existing_pr(data.get("branch", ""))
    if existing_url:
        info(f"PR already exists: {existing_url}")
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

    plugin = select_plugin(DraftPrPlugin, configured_plugin_name)
    if plugin is None:
        error("Error: no plugins registered.")
        error("Install a plugin with: brew install <plugin-formula>")
        error("Or run 'devflow-plugin list' to see what is installed.")
        sys.exit(1)

    # Standard inputs
    jira, github_issue = resolve_jira(data, args.github_issue)
    standard_answers = prompt(build_questions(data))
    jira = standard_answers.get("jira_ticket") or jira   # user may have typed it
    issue_type = standard_answers.get("issue_type") or data.get("issue_type", "Issue")
    answer = select("Is this a customer-visible change?", choices=["Yes", "No"], single=True)
    customer_visible = "yes" if answer == "Yes" else "no"

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
        error(f"AI error: {ai_result.error}")
        sys.exit(1)

    body_str = plugin.build_body(ai_result.result, user_inputs)
    title = ai_result.result.get("title", "") if isinstance(ai_result.result, dict) else ""

    os.makedirs(TMP_DIR, exist_ok=True)
    body_path = os.path.join(TMP_DIR, "pr-body.md")
    script_path = os.path.join(TMP_DIR, "create-pr.sh")

    with open(body_path, "w") as f:
        f.write(body_str)

    write_create_script(title, body_path, script_path, base=data.get("base"))
    url, error_msg = run_create_script(script_path)
    if url:
        success(f"PR created: {url}")
        summary.add("PR", url)
        branch = data.get("branch")
        if branch:
            summary.add("Branch", branch)
    elif error_msg:
        error(f"PR creation failed: {error_msg}")
        error(f"Run manually: bash {script_path}")


if __name__ == "__main__":
    main()
