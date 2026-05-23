# Internal Developer Notes

> INTERNAL DEVELOPMENT-PROCESS ARTIFACTS
>
> These documents preserve project coordination, RoleThread validation context,
> and handoff notes. They are intentionally excluded from source distributions
> and are not part of the public user documentation surface.

This directory is for practical integration and release-readiness work. The
documents are tracked so a fresh clone has the working context, but they should
not be treated as user documentation, support promises, or public API
guarantees.

## Scope

Use these notes for:

- RoleThread integration planning.
- package rehearsal coordination.
- runtime validation notes.
- Codex handoff continuity between sessions.
- temporary experiments around integration boundaries.

Do not use these notes as:

- public installation documentation.
- stable architecture reference.
- permanent support promises.
- evidence that future features already exist.

## Documents

- [RoleThread Integration Plan](rolethread_integration_plan.md)
- [RoleThread Handoff Checklist](rolethread_handoff_checklist.md)
- [RoleThread Runtime Mapping](rolethread_runtime_mapping.md)
- [RoleThread Test Matrix](rolethread_test_matrix.md)
- [RoleThread / LitLaunch Manual Test Plan](rolethread_litlaunch_manual_test_plan.md)
- [Release Validation Notes](release_validation_notes.md)

## Maintenance Expectation

Review this directory before public releases. Public architecture truths should
live in `docs/architecture.md` and `docs/philosophy.md`, not here. If a note
becomes long-lived user guidance, promote it into the public docs and remove the
process-only wording.
