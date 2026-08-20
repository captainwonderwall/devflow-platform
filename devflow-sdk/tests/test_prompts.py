from unittest.mock import patch

from devflow_sdk.prompts import select, checkbox, text, confirm, prompt, Choice


class TestText:
    @patch("devflow_sdk.prompts.questionary.text")
    def test_returns_questionary_result(self, mock_text):
        mock_text.return_value.ask.return_value = "VDP-123"
        result = text("Enter issue:")
        assert result == "VDP-123"
        mock_text.assert_called_once_with("Enter issue:")

    @patch("devflow_sdk.prompts.questionary.text")
    def test_returns_none_on_cancel(self, mock_text):
        mock_text.return_value.ask.return_value = None
        result = text("Enter issue:")
        assert result is None


class TestSelect:
    @patch("devflow_sdk.prompts.questionary.select")
    def test_returns_questionary_result(self, mock_select):
        mock_select.return_value.ask.return_value = "Yes"
        result = select("Pick one", ["Yes", "No"])
        assert result == "Yes"
        mock_select.assert_called_once_with("Pick one", choices=["Yes", "No"])

    @patch("devflow_sdk.prompts.questionary.select")
    def test_returns_none_on_cancel(self, mock_select):
        mock_select.return_value.ask.return_value = None
        result = select("Pick one", ["Yes", "No"])
        assert result is None


class TestConfirm:
    @patch("devflow_sdk.prompts.questionary.confirm")
    def test_returns_true_on_yes(self, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        result = confirm("Push?")
        assert result is True
        mock_confirm.assert_called_once_with("Push?", default=False)

    @patch("devflow_sdk.prompts.questionary.confirm")
    def test_returns_false_on_no(self, mock_confirm):
        mock_confirm.return_value.ask.return_value = False
        result = confirm("Push?")
        assert result is False

    @patch("devflow_sdk.prompts.questionary.confirm")
    def test_returns_none_on_cancel(self, mock_confirm):
        mock_confirm.return_value.ask.return_value = None
        result = confirm("Push?")
        assert result is None

    @patch("devflow_sdk.prompts.questionary.confirm")
    def test_passes_through_default(self, mock_confirm):
        mock_confirm.return_value.ask.return_value = True
        confirm("Push?", default=True)
        mock_confirm.assert_called_once_with("Push?", default=True)


class TestPrompt:
    @patch("devflow_sdk.prompts.questionary.prompt")
    def test_builds_text_questions_and_returns_answers(self, mock_prompt):
        mock_prompt.return_value = {"jira_ticket": "VDP-123"}
        result = prompt([{"id": "jira_ticket", "text": "Jira ticket?"}])
        assert result == {"jira_ticket": "VDP-123"}
        mock_prompt.assert_called_once_with(
            [{"type": "text", "name": "jira_ticket", "message": "Jira ticket?"}]
        )

    @patch("devflow_sdk.prompts.questionary.prompt")
    def test_returns_empty_dict_on_cancel(self, mock_prompt):
        mock_prompt.return_value = None
        result = prompt([{"id": "jira_ticket", "text": "Jira ticket?"}])
        assert result == {}


class TestCheckboxWithoutResolve:
    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_returns_raw_checked_list(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["a", "b"]
        result = checkbox("Pick some", [Choice(title="a", value="a")])
        assert result == ["a", "b"]

    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_returns_none_on_cancel(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = None
        result = checkbox("Pick some", [Choice(title="a", value="a")])
        assert result is None


class TestCheckboxWithResolve:
    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_returns_none_on_cancel_without_calling_resolve(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = None
        resolve_calls = []

        def resolve(checked):
            resolve_calls.append(checked)
            return checked, None

        result = checkbox("Pick some", [], resolve=resolve)
        assert result is None
        assert resolve_calls == []

    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_returns_result_on_success(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = ["1"]
        result = checkbox("Pick some", [], resolve=lambda checked: ([0], None))
        assert result == [0]

    @patch("builtins.print")
    @patch("devflow_sdk.prompts.questionary.checkbox")
    def test_reprompts_on_error_then_succeeds(self, mock_checkbox, mock_print):
        mock_checkbox.return_value.ask.side_effect = [["bad"], ["1"]]
        resolve = lambda checked: (None, "bad input") if checked == ["bad"] else ([0], None)

        result = checkbox("Pick some", [], resolve=resolve)

        assert result == [0]
        assert mock_checkbox.return_value.ask.call_count == 2
        mock_print.assert_any_call("bad input")
