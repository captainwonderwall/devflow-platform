import glob as _glob, os as _os, sys as _sys
_vendor = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "vendor")
for _whl in _glob.glob(_os.path.join(_vendor, "*.whl")):
    if _whl not in _sys.path:
        _sys.path.insert(0, _whl)
del _glob, _os, _sys, _vendor

from devflow_sdk.plugin import DraftPrPlugin


class SmokePlugin(DraftPrPlugin):
    name = "Smoke Check"

    def get_questions(self, data: dict) -> list[dict]:
        return []

    def build_prompt(self, data: dict, user_inputs: dict) -> str:
        # Return an AI prompt string. draft-pr passes this to run_ai_prompt.
        # data keys: git_log, diff_stat, changed_files, branch, is_fix, ...
        # user_inputs keys: jira_ticket, github_issue, issue_type, customer_visible, ...
        # The JSON keys you ask for here are what build_body receives in ai_result.
        return (
            "Output ONLY a JSON object with keys title and description:\n"
            + data["git_log"]
        )

    def build_body(self, ai_result: dict, user_inputs: dict) -> str:
        # Render the PR body markdown from ai_result.
        return f"## {ai_result['title']}\n\n{ai_result['description']}\n"
