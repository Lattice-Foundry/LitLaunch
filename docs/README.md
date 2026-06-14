# LitLaunch Documentation Map

LitLaunch follows the workspace Profile A documentation structure.

## Public Docs

Public documentation lives under `docs/Public/**`:

- [Guides](Public/Guides/)
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

If durable internal records are needed later, use the approved standard folders
such as `docs/architecture/`, `docs/audits/`, `docs/research/`,
`docs/planning/`, `docs/testing/`, `docs/security/`, `docs/release/`, or
`docs/archive/`, and keep them public-repo safe before tracking.
