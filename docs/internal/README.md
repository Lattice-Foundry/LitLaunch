# Internal Developer Notes

> INTERNAL DEVELOPMENT-PROCESS ARTIFACTS
>
> These documents preserve project coordination, audits, research, roadmap,
> validation, and handoff context. They are intentionally excluded from source
> distributions and are not part of the public user documentation surface.

This directory is the home for LitLaunch internal working material. Public user
documentation should stay in the top-level `docs/` files and public
subdirectories. Internal notes should use the lanes below instead of returning
to a root-level `notes/` directory.

## Lanes

### Architecture

Private design notes, integration boundaries, runtime mappings, and internal
architecture decisions.

- [RoleThread Integration Plan](architecture/rolethread_integration_plan.md)
- [RoleThread Runtime Mapping](architecture/rolethread_runtime_mapping.md)

### Audits

Internal audits, weakness hunts, third-party review prep, and release-readiness
reviews.

- [LitLaunch DOMINATE Audit](audits/litlaunch_dominate_audit.md)
- [LitLaunch Security Audit 0.91.23b1](audits/litlaunch_security_audit_0_91_23b1.md)
- [RoleThread Pre-Publish Weakness Hunt](audits/rolethread_pre_publish_weakness_hunt.md)

### Research

Recon notes, visible-surface reviews, CLI reviews, future ideas, and exploratory
technical notes.

- [CLI Surface Recon](research/cli_surface_recon.md)
- [Visible Surface Recon](research/visible_surface_recon.md)

### Roadmap

Handoff checklists, future development plans, and launch coordination.

- [RoleThread Handoff Checklist](roadmap/rolethread_handoff_checklist.md)

### Validation

Manual test plans, runtime validation, compatibility matrices, and release
validation notes.

- [Release Validation Notes](validation/release_validation_notes.md)
- [RoleThread / LitLaunch Manual Test Plan](validation/rolethread_litlaunch_manual_test_plan.md)
- [RoleThread Test Matrix](validation/rolethread_test_matrix.md)

### Assets

Internal evidence files such as screenshots used by audits or research notes.

- [Light Theme Screenshots](assets/light_theme/)

## Maintenance Expectations

- Keep public architecture truths in `docs/architecture.md` and
  `docs/philosophy.md`, not here.
- Promote long-lived user guidance into the public docs and remove
  process-only wording.
- Keep local scratch notes out of the repo root; use these lanes when a note is
  worth preserving.
- Review this directory before public releases. It is excluded from package
  artifacts, but it may still be visible in repository history.
