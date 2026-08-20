from abc import ABC, abstractmethod


class PluginBase(ABC):
    name: str = ""

    @abstractmethod
    def get_questions(self, data: dict) -> list[dict]:
        """Return questions to ask the user before calling the AI.

        Each dict must have:
          id: str   — used as the key in user_inputs
          text: str — displayed to the user
        """

    @abstractmethod
    def build_prompt(self, data: dict, user_inputs: dict) -> str:
        """Build and return the AI prompt string.

        data: output of gather_pr_data.collect() — keys include
              git_log, diff_stat, changed_files, branch, base, is_fix
        user_inputs: answers to get_questions(), keyed by question id,
                     plus any standard inputs (jira, issue_type,
                     customer_visible)
        """

    @abstractmethod
    def build_body(self, ai_result: dict, user_inputs: dict) -> str:
        """Render and return the PR body markdown.

        ai_result: parsed JSON dict returned by the AI — schema is
                   whatever your build_prompt asked for
        user_inputs: same dict passed to build_prompt
        """
