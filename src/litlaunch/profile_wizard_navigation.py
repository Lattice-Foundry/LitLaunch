"""Navigation helpers for the profile wizard."""

from __future__ import annotations

from litlaunch.profile_wizard_state import WizardState, WizardStep


def previous_step_index(
    steps: tuple[WizardStep, ...],
    state: WizardState,
    index: int,
) -> int:
    """Return the nearest previous visible wizard step index."""

    for previous in range(index - 1, -1, -1):
        if not steps[previous].skip(state):
            return previous
    return index
