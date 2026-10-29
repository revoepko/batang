# Codex project instructions example

This Markdown is for Codex to read. It is not a machine-readable configuration file and this package has no YAML configuration loader. Copy or merge only the sections needed into the target project's existing `AGENTS.md`; do not replace the whole file. Use paths confirmed for that project and vault.

## Batang values

```yaml
batang:
  knowledge_root: /absolute/path/to/selected-vault
  active_index: ACTIVE.md
  backup_root: /absolute/path/to/approved-backups
  graphify_executable: /absolute/path/to/graphify
  graph_output: /absolute/path/to/approved-output/graph.json
  archify_executable: /absolute/path/to/archify.mjs
  source_roots:
    123e4567-e89b-42d3-a456-426614174000: /absolute/path/to/selected-source-root
```

Use `source_roots` only for source roots that the user has selected. Map the generated root identifier to the corresponding actual local path; do not put that absolute path in shared notes. A mapping is not permission to read the source. The project owner selects and prepares `backup_root` in an approved location; the file helper does not create parent directories. `graph_output` is an absolute path to a JSON file. The Graphify executable and Archify script must already be available at their configured paths. Archify uses the host's existing Node runtime; do not add a wrapper or installer. Tested external versions and runtime notes are in [THIRD_PARTY.md](../THIRD_PARTY.md).

`active_index` names the list of Markdown files allowed for the workflow. For example, `ACTIVE.md` can contain:

```markdown
- [Topic](notes/topic.md)
```

The link is relative to `knowledge_root`. Use only listed files and material the user selects for the request. Selecting a vault does not grant access to every note.

For role recommendations, allowed alternatives, reasoning levels, and selection criteria, merge with existing project policy only at installation, first use, or a relevant environment or policy change. Preserve mandatory project models and modes. The parent chooses an available permitted alternative; record the assignment and reason in the plan and actual invocation in the run. This file grants no runtime permissions.

## Existing vault and tools

- For selected existing notes, follow [the import contract](../skills/batang/references/import.md); copy independent bytes and leave originals unchanged.
- Preserve the existing vault's folders, notes, frontmatter, `.obsidian` settings, and active list. Do not import the whole vault.
- If the active list is missing or conflicts with the request, propose its exact path and included files. Create or replace it only after explicit approval.
- If the user has no vault, ask for its name, parent directory, and whether to create it. Create only the agreed empty structure after explicit approval.
- The host must have access to the selected Obsidian Markdown and prepared Graphify and Archify paths before setup is considered ready. Obsidian app registration or opening is separate; the host reads Markdown directly. Graphify supports relationship work and approved refreshes. Run Archify only for a requested explanation or diagram.
- During ordinary use, do not search arbitrary paths, install or upgrade tools, or switch providers. If a configured tool is unavailable, report the missing path or access. For an explicit setup request, follow [installation instructions](../AGENTS.md) and prepare missing tools only within the user-selected or already approved scope.
- Register only the Batang skill. For a task that uses Madi, read its internal workflow from the same checkout and revision. Verify every file against the root `SHA256SUMS`, then record that file's SHA-256 as the bundle identity. Keep release `candidate-manifest.json` and archive hashes as separate candidate evidence.
- Preserve existing profiles, in-progress runs, knowledge files, and installed registrations. Do not silently move them to a newer checkout.

## Optional project checker recommendation

“Optional” here means that adding this recommended text to the project's instructions is the user's choice. It does not waive any review required by the selected Madi work or the project plan. For ordinary documentation or diagram work, record in the plan whether separate quality or security review is needed and why. Keep the author separate from any required reviewer. Public code release still requires an independent read-only security review of the entire fixed candidate.

This example is not itself installed. First compare it with the target project's actual instructions and show the proposed change. Apply only the selected project-local change; do not modify global settings or agent TOML files.

```markdown
## Batang review requirements

- Follow the host's existing subagent rules and permissions. These project instructions do not change global settings, model availability, or Daybreak access.
- `quality_checker` and `security_checker` name review responsibilities, not required Codex agent profile names. An available `default`, `worker`, `explorer`, or other host role can perform a required review only when the actual call is independent and meets the required model and mode. Custom TOML profiles are optional.
- For Madi development work, quality review is required. The public recommendation is standard mode `gpt-6.1-sol/high`; project-mandated models and modes take precedence. The parent selects an available alternative only when permitted. If the required review cannot be verified, record the gate as blocked.
- For a required security review, the public recommendation is Daybreak `gpt-6-sol/high` only when access, model compatibility, and actual mode are verified. Otherwise the recommendation is standard `gpt-6.1-sol/high` for the same entire fixed candidate when the host can make that call; preserve mandatory project requirements and use only permitted alternatives. Preserve failed access attempts and review findings.
- Every task using the internal Madi workflow requires review independent of its author. Public code release also requires the independent security review of the entire fixed candidate. For ordinary documentation and diagram work, the project plan determines whether additional quality or security review is needed and records the reason; it does not waive the independent review.
- In a new run using Madi, verify the actual policy paths, candidate manifest, and reviewer invocation. A profile name or settings file alone does not prove that a review ran.
```
