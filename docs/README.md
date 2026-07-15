# LitLaunch Documentation Map

LitLaunch follows the workspace Profile A documentation structure.

## Public Docs

Public documentation lives under `docs/Public/**`:

- [Guides](Public/Guides/)
- [Experimental Initial Host Sizing](Public/Guides/host-sizing.md)
- [Integration Guides](Public/Guides/integration/)
- [Reference](Public/Reference/)
- [Troubleshooting](Public/Troubleshooting/)
- [FAQ](Public/FAQ/)
- [Help](Public/Help/)

## Project Records

The local documentation rulebook is
[docs_structure_standard.md](docs_structure_standard.md).

`docs/internal/**` is intentionally absent from tracked public source after the
2026-06-14 public exposure remediation pass. Private, local, and scratch notes
belong in ignored lanes such as `notes/`, `docs/private/`, `docs/local/`,
`docs/**/scratch/`, `docs/**/tmp/`, and `docs/**/inbox/`.

Approved internal record folders are present with `.gitkeep` placeholders:

- `docs/architecture/`
- `docs/audits/`
- `docs/planning/`
- `docs/research/`
- `docs/implementation/`
- `docs/migrations/`
- `docs/release/`
- `docs/security/`
- `docs/testing/`
- `docs/archive/`

Use these only for durable records that are safe for a public repository.
