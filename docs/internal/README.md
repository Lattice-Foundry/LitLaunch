# Internal Integration Documentation

> INTERNAL / TEMPORARY INTEGRATION DOCUMENTATION
>
> These documents exist to support LitLaunch beta integration workflows and
> ecosystem validation. They are intentionally excluded from the stable public
> documentation surface and may change substantially before release
> stabilization.

This directory is for practical integration work while LitLaunch is being
validated with RoleThread, TestPyPI rehearsals, and beta runtime smoke testing.
The documents are tracked so a fresh clone has the working context, but they
should not be treated as stable user documentation or public API guarantees.
They are excluded from public source distributions.

## Scope

Use these notes for:

- RoleThread integration planning.
- TestPyPI rehearsal coordination.
- beta runtime validation.
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
- [Known Beta Issues](known_beta_issues.md)

## Removal Expectation

Before release stabilization, decide whether this directory should be removed,
collapsed into issue tracker tasks, or split into permanent public docs and
private integration notes. Public architecture truths should live in
`docs/architecture.md` and `docs/philosophy.md`, not here.
