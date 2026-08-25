from smoke_check import SmokePlugin


def test_build_body_contains_title():
    plugin = SmokePlugin()
    ai_result = {"title": "Fix login", "description": "Fixes the login flow"}
    body = plugin.build_body(ai_result, user_inputs={})
    assert "Fix login" in body


def test_build_body_contains_description():
    plugin = SmokePlugin()
    ai_result = {"title": "Fix login", "description": "Fixes the login flow"}
    body = plugin.build_body(ai_result, user_inputs={})
    assert "Fixes the login flow" in body


def test_build_prompt_returns_string():
    plugin = SmokePlugin()
    data = {
        "git_log": "abc123 Fix auth",
        "diff_stat": "1 file changed",
        "changed_files": ["src/auth.py"],
    }
    prompt = plugin.build_prompt(data, user_inputs={})
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_get_questions_returns_list():
    plugin = SmokePlugin()
    result = plugin.get_questions({})
    assert isinstance(result, list)
