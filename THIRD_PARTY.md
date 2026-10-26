# Third-party notices

## Materials in this repository

All Batang materials in this repository are provided under the [MIT License](LICENSE). The copyright notice is `Copyright (c) 2026 EPKO`.

The package does not include a user's vault, notes, operational records, backups, or implementations of external tools.

## Tools required for setup

The host must have access to the selected Obsidian Markdown and configured Graphify and Archify paths before the supported workflow is ready. This is a preparation requirement, not a promise that all tools run on every request. Obsidian is not opened or registered automatically; Graphify is used for relationship work and approved refreshes; Archify runs only for a requested explanation or diagram.

| Tool | Tested upstream version | Host preparation and use | Included in this package |
|---|---|---|---|
| Obsidian | App 1.12.7 | The host accesses the selected vault's Markdown directly. App registration and sync are managed by the user or host. | No app, vault, or user notes. |
| Graphify | [`Graphify-Labs/graphify`](https://github.com/Graphify-Labs/graphify), distribution `graphifyy` 0.9.92, commit `86c57be8204673c2a1b9849a3292a7dd3ab373d8` | Existing host executable and output path; tested on macOS ARM64 with Python 3.14.7. Used for relationship work and approved refreshes. Upstream notices include Apache-2.0 and the existing MIT portions' NOTICE and LICENSE-MIT. | No implementation, runtime, or graph data. |
| Archify | [`tt-a1i/archify`](https://github.com/tt-a1i/archify), 3.2.0 / skill 3.2, commit `654da74e084e5a1faf708779c23d6172766be9c1` | Existing host script path and Node 24.13.0 runtime; invoked only for a requested explanation or diagram. The skill source uses MIT. | No implementation, runtime, or generated output. |

The internal `skills/batang/scripts/file_ops.py` helper uses Python's standard library and does not require PyYAML. The helper does not pin a separate Python runtime version. Graphify's runtime is supplied by the existing host installation; this package does not install it or bundle its Python packages. The host remains responsible for its configured runtime and dependencies.

This notice records the versions and upstream notices used for the supported environment. It does not replace the terms or notices of the upstream projects.
