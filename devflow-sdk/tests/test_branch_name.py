import unittest


from devflow_sdk.branch_name import infer_type, slugify, make_branch, parse_branch


class TestInferType(unittest.TestCase):
    def test_jira_bug_type_returns_fix(self):
        self.assertEqual(infer_type({"issuetype": "Bug", "labels": []}), "fix")

    def test_jira_defect_type_returns_fix(self):
        self.assertEqual(infer_type({"issuetype": "Defect", "labels": []}), "fix")

    def test_jira_story_type_returns_feat(self):
        self.assertEqual(infer_type({"issuetype": "Story", "labels": []}), "feat")

    def test_jira_task_type_returns_feat(self):
        self.assertEqual(infer_type({"issuetype": "Task", "labels": []}), "feat")

    def test_empty_issuetype_returns_feat(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": []}), "feat")

    def test_github_bug_label_returns_fix(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["bug"]}), "fix")

    def test_github_fix_label_returns_fix(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["fix"]}), "fix")

    def test_github_defect_label_returns_fix(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["defect"]}), "fix")

    def test_github_unrelated_labels_returns_feat(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["enhancement", "docs-typo"]}), "feat")

    def test_bug_type_case_insensitive(self):
        self.assertEqual(infer_type({"issuetype": "BUG", "labels": []}), "fix")

    def test_label_case_insensitive(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["Bug"]}), "fix")

    def test_hotfix_label_returns_hotfix(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["hotfix"]}), "hotfix")

    def test_urgent_label_returns_hotfix(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["urgent"]}), "hotfix")

    def test_hotfix_issuetype_returns_hotfix(self):
        self.assertEqual(infer_type({"issuetype": "Hotfix", "labels": []}), "hotfix")

    def test_docs_label_returns_docs(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["docs"]}), "docs")

    def test_documentation_label_returns_docs(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["documentation"]}), "docs")

    def test_chore_label_returns_chore(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["chore"]}), "chore")

    def test_maintenance_label_returns_chore(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["maintenance"]}), "chore")

    def test_hotfix_takes_precedence_over_fix(self):
        # a ticket labeled both bug and hotfix should resolve to hotfix
        self.assertEqual(infer_type({"issuetype": "", "labels": ["bug", "hotfix"]}), "hotfix")

    def test_fix_takes_precedence_over_docs(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["bug", "docs"]}), "fix")

    def test_docs_takes_precedence_over_chore(self):
        self.assertEqual(infer_type({"issuetype": "", "labels": ["docs", "chore"]}), "docs")


class TestSlugify(unittest.TestCase):
    def test_basic_lowercase_hyphen(self):
        self.assertEqual(slugify("Start Issue Script"), "start-issue-script")

    def test_strips_special_characters(self):
        self.assertEqual(slugify("Fix: null-pointer on login!"), "fix-null-pointer-on-login")

    def test_caps_at_six_words(self):
        result = slugify("one two three four five six seven eight")
        self.assertEqual(result, "one-two-three-four-five-six")

    def test_custom_max_words(self):
        self.assertEqual(slugify("one two three four", max_words=2), "one-two")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "")

    def test_all_special_chars(self):
        self.assertEqual(slugify("!!!"), "")

    def test_numbers_preserved(self):
        self.assertEqual(slugify("Fix 404 error"), "fix-404-error")


class TestMakeBranch(unittest.TestCase):
    def _jira_issue(self, issuetype="Story", labels=None, id="VDP-46625",
                     title="Build start issue script"):
        return {"issuetype": issuetype, "labels": labels or [], "id": id,
                "title": title, "source": "jira"}

    def _gh_issue(self, issuetype="", labels=None, id="42",
                  title="Add export button"):
        return {"issuetype": issuetype, "labels": labels or [], "id": id,
                "title": title, "source": "github"}

    def test_feat_prefix_for_story_jira(self):
        result = make_branch(self._jira_issue())
        self.assertEqual(result, "feat/jira-VDP-46625-build-start-issue-script")

    def test_fix_prefix_for_bug_jira(self):
        result = make_branch(self._jira_issue(issuetype="Bug"))
        self.assertEqual(result, "fix/jira-VDP-46625-build-start-issue-script")

    def test_override_feat_forces_feat_on_bug(self):
        result = make_branch(self._jira_issue(issuetype="Bug"), override="feat")
        self.assertEqual(result, "feat/jira-VDP-46625-build-start-issue-script")

    def test_override_hotfix(self):
        result = make_branch(self._jira_issue(), override="hotfix")
        self.assertEqual(result, "hotfix/jira-VDP-46625-build-start-issue-script")

    def test_override_docs(self):
        result = make_branch(self._jira_issue(), override="docs")
        self.assertEqual(result, "docs/jira-VDP-46625-build-start-issue-script")

    def test_override_chore(self):
        result = make_branch(self._jira_issue(), override="chore")
        self.assertEqual(result, "chore/jira-VDP-46625-build-start-issue-script")

    def test_github_issue_format(self):
        result = make_branch(self._gh_issue())
        self.assertEqual(result, "feat/gh42-add-export-button")

    def test_title_truncated_to_six_words(self):
        issue = self._jira_issue(title="one two three four five six seven eight")
        result = make_branch(issue)
        self.assertEqual(result, "feat/jira-VDP-46625-one-two-three-four-five-six")

    def test_worktree_true_adds_wt_segment_github(self):
        result = make_branch(self._gh_issue(), worktree=True)
        self.assertEqual(result, "feat/wt/gh42-add-export-button")

    def test_worktree_true_adds_wt_segment_jira(self):
        result = make_branch(self._jira_issue(), worktree=True)
        self.assertEqual(result, "feat/wt/jira-VDP-46625-build-start-issue-script")

    def test_worktree_false_omits_wt_segment(self):
        result = make_branch(self._gh_issue(), worktree=False)
        self.assertNotIn("/wt/", result)


class TestParseBranch(unittest.TestCase):
    def test_parses_github_no_worktree(self):
        result = parse_branch("feat/gh42-add-export-button")
        self.assertEqual(result, {
            "type": "feat", "is_worktree": False,
            "source": "github", "id": "42", "slug": "add-export-button",
        })

    def test_parses_github_with_worktree(self):
        result = parse_branch("hotfix/wt/gh99-fix-prod-outage")
        self.assertEqual(result, {
            "type": "hotfix", "is_worktree": True,
            "source": "github", "id": "99", "slug": "fix-prod-outage",
        })

    def test_parses_jira_no_worktree(self):
        result = parse_branch("fix/jira-VDP-46625-build-start-issue-script")
        self.assertEqual(result, {
            "type": "fix", "is_worktree": False,
            "source": "jira", "id": "VDP-46625", "slug": "build-start-issue-script",
        })

    def test_parses_jira_with_worktree(self):
        result = parse_branch("docs/wt/jira-VDP-1-update-readme")
        self.assertEqual(result, {
            "type": "docs", "is_worktree": True,
            "source": "jira", "id": "VDP-1", "slug": "update-readme",
        })

    def test_parses_all_five_types(self):
        for t in ("feat", "fix", "hotfix", "chore", "docs"):
            result = parse_branch(f"{t}/gh1-x")
            self.assertEqual(result["type"], t)

    def test_round_trips_make_branch_output(self):
        issue = {"issuetype": "Bug", "labels": [], "id": "7",
                  "title": "Crash on save", "source": "github"}
        branch = make_branch(issue, worktree=True)
        parsed = parse_branch(branch)
        self.assertEqual(parsed["type"], "fix")
        self.assertEqual(parsed["is_worktree"], True)
        self.assertEqual(parsed["source"], "github")
        self.assertEqual(parsed["id"], "7")

    def test_returns_none_for_old_format_branch(self):
        # old format had no source tag: feat/42-slug
        self.assertIsNone(parse_branch("feat/42-add-export-button"))

    def test_returns_none_for_unrelated_branch(self):
        self.assertIsNone(parse_branch("main"))

    def test_returns_none_for_unknown_type(self):
        self.assertIsNone(parse_branch("refactor/gh1-x"))

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(parse_branch(""))

    def test_returns_none_for_none(self):
        self.assertIsNone(parse_branch(None))


if __name__ == "__main__":
    unittest.main()
