try:
    import questionary
except ImportError as e:
    raise SystemExit(
        "Missing dependency: questionary. Install it with: pip install questionary"
    ) from e

Choice = questionary.Choice


def text(message):
    """Free-text prompt. Returns the entered string, or None if the user
    cancelled (Ctrl+C)."""
    return questionary.text(message).ask()


def select(message, choices):
    """Single-select prompt. Returns the chosen value, or None if the
    user cancelled (Ctrl+C)."""
    return questionary.select(message, choices=choices).ask()


def confirm(message, default=False):
    """Yes/No prompt. Returns True if the user chose Yes, False for No,
    or None if the user cancelled (Ctrl+C)."""
    return questionary.confirm(message, default=default).ask()


def prompt(questions):
    """Batch text-input prompt. `questions` is a list of {id, text} dicts.
    Returns a dict of {id: answer}, or an empty dict if the user cancelled."""
    qs = [{"type": "text", "name": q["id"], "message": q["text"]} for q in questions]
    return questionary.prompt(qs) or {}


def checkbox(message, choices, resolve=None):
    """Multi-select checkbox prompt.

    Without `resolve`: asks once and returns the raw list of checked
    values (or None if the user cancelled).

    With `resolve`: loops -- ask, then call `resolve(checked)`, which
    must return a (result, error) tuple. If error is not None, it is
    printed and the prompt repeats. Otherwise `result` is returned. If
    the user cancels (Ctrl+C, raw value is None), returns None
    immediately without calling `resolve`.
    """
    while True:
        checked = questionary.checkbox(message, choices=choices).ask()
        if resolve is None:
            return checked
        if checked is None:
            return None
        result, error = resolve(checked)
        if error is not None:
            print(error)
            continue
        return result
