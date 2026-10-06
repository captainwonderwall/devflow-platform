try:
    import questionary
except ImportError as e:
    raise SystemExit(
        "Missing dependency: questionary. Install it with: pip install questionary"
    ) from e

Choice = questionary.Choice


def text(message, default=""):
    """Free-text prompt. Returns the entered string, or None if the user
    cancelled (Ctrl+C)."""
    return questionary.text(message, default=default).ask()


def _patch_checkbox_for_radio(q):
    """Modify a questionary.checkbox Question to behave as a radio group.

    Replaces the space-toggle binding so that pressing space on an item
    deselects any previously selected item before selecting the new one.
    Also removes the toggle-all (a) and invert (i) bindings, which have no
    meaning in single-select mode.
    """
    from questionary.prompts.common import InquirerControl

    app = q.application
    kb = app.key_bindings
    ic = next(
        (c for c in app.layout.find_all_controls() if isinstance(c, InquirerControl)),
        None,
    )
    if ic is None:
        return

    for binding in list(kb.bindings):
        if binding.keys in ((" ",), ("a",), ("i",)):
            kb.remove(binding.handler)

    @kb.add(" ", eager=True)
    def _radio_toggle(_event):
        pointed_value = ic.get_pointed_at().value
        if ic.selected_options == [pointed_value]:
            ic.selected_options = []
        else:
            ic.selected_options = [pointed_value]


def select(message, choices, single=False):
    """Single-select prompt using checkbox UI. Exactly one item must be
    chosen. Re-prompts on empty selection. Returns the chosen value, or
    None if the user cancelled (Ctrl+C).

    With single=True, selecting one item automatically deselects any
    previously selected item (radio-button behavior).
    """
    while True:
        q = questionary.checkbox(message, choices=choices)
        if single:
            _patch_checkbox_for_radio(q)
        checked = q.ask()
        if checked is None:
            return None
        if len(checked) == 0:
            print("Select one option.")
            continue
        if len(checked) > 1:
            print("Select only one option.")
            continue
        return checked[0]


def confirm(message, default=False):
    """Yes/No prompt. Returns True if the user chose Yes, False for No,
    or None if the user cancelled (Ctrl+C)."""
    return questionary.confirm(message, default=default).ask()


def prompt(questions):
    """Batch text-input prompt. `questions` is a list of {id, text} dicts.
    Returns a dict of {id: answer}, or an empty dict if the user cancelled."""
    qs = [{"type": "text", "name": q["id"], "message": q["text"]} for q in questions]
    return questionary.prompt(qs) or {}


def checkbox(message, choices, resolve=None, allow_empty=False):
    """Multi-select checkbox prompt. By default at least one item must be
    chosen; pass allow_empty=True to accept zero selections. Re-prompts on
    empty selection when allow_empty is False. Returns the list of checked
    values, or None if the user cancelled (Ctrl+C).

    With `resolve`: after a non-empty selection, calls
    `resolve(checked)`, which must return a (result, error) tuple.
    If error is not None it is printed and the prompt repeats.
    """
    while True:
        checked = questionary.checkbox(message, choices=choices).ask()
        if checked is None:
            return None
        if not checked and not allow_empty:
            print("Select at least one option.")
            continue
        if resolve is None:
            return checked
        result, error = resolve(checked)
        if error is not None:
            print(error)
            continue
        return result
