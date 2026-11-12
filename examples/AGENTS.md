# Project instructions example

This Markdown is a reference for the selected host. It is not a machine-readable configuration file and this package has no YAML configuration loader. Copy or merge only the sections needed into the target project's applicable existing policy file; do not replace the whole file. Use paths confirmed for that project and vault. Apply Batang-specific instructions only when the user explicitly invokes Batang and for follow-ups to that same task; retain general personal and project rules, roles, and permissions for all tasks.

Merge the needed instructions into the project's applicable `AGENTS.md`. Registering the skill is a separate step described in the [Codex guide](../skills/batang/references/hosts/codex.md).

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

Use `source_roots` only for source roots that the user has selected. Map the generated root identifier to the corresponding actual local path; do not put that absolute path in shared notes. A mapping is not permission to read the source. The project owner selects and prepares `backup_root` in an approved location; the file helper does not create parent directories. `graph_output` is an absolute path to a JSON file. For relationship work, the Graphify executable and Python must be available at their configured paths; requested visualization needs the Archify script and Node. Direct Markdown lookup needs neither. Archify uses the host's existing Node runtime; do not add a wrapper or installer. Tested external versions and runtime notes are in [THIRD_PARTY.md](../THIRD_PARTY.md).

`active_index` names the list of Markdown files allowed for the workflow. For example, `ACTIVE.md` can contain:

```markdown
- [Topic](notes/topic.md)
```

The link is relative to `knowledge_root`. Use only listed files and material the user selects for the request. Selecting a vault does not grant access to every note.

For Batang role recommendations, allowed alternatives, reasoning levels, and selection criteria, merge with existing project policy only at installation, first use, or a relevant environment or policy change. Preserve mandatory project models and modes. The parent chooses an available permitted alternative; record the assignment and reason in the plan and actual invocation in the run. This file grants no runtime permissions.

## Existing vault and tools

Apply these Batang-specific procedures when the user explicitly invokes Batang and during follow-ups to that same task.

- For selected existing notes, follow [the import contract](../skills/batang/references/import.md); copy independent bytes and leave originals unchanged.
- Preserve the existing vault's folders, notes, frontmatter, `.obsidian` settings, and active list. Do not import the whole vault.
- If the active list is missing or conflicts with the request, propose its exact path and included files. Create or replace it only after explicit approval.
- If the user has no vault, ask for its name, parent directory, and whether to create it. Create only the agreed empty structure after explicit approval.
- Prepare only the materials and tools needed for the request: the selected vault and active list for knowledge work, Graphify and Python for relationship work, and Archify and Node for requested visualization. Independent code or document work does not require an operational vault. Obsidian app registration or opening is separate; the host reads Markdown directly.
- During ordinary use, do not search arbitrary paths, install or upgrade tools, or switch providers. If a configured tool is unavailable, report the missing path or access. For an explicit setup request, follow [installation instructions](../AGENTS.md) and prepare missing tools only within the user-selected or already approved scope.
- Register only the Batang skill. For a task that uses Madi, read its internal workflow from the same checkout and revision. Reuse valid verification evidence for the same fixed checkout across runs. On a new registration selection, installation, transfer, relevant change, error or uncertainty, verify every root `SHA256SUMS` entry and that file itself again; record its SHA-256 as the bundle identity. Keep release `candidate-manifest.json` and archive hashes as separate candidate evidence.
- Preserve existing profiles, in-progress runs, knowledge files, and installed registrations. Do not silently move them to a newer checkout.

## Delegation and review

Apply the Batang-specific delegation and review procedures below to an explicitly invoked Batang task and its follow-ups. General host, personal, and project rules and existing roles remain in effect.

When approved for the host, merge this limited entry provision into its existing applicable instructions: “For an explicitly invoked Batang task and its follow-ups, apply the [Batang delegation guidance](../skills/batang/references/delegation.md) to the permitted defaults for work decomposition, role selection, and optional review assignment. Preserve higher-priority instructions, permissions, mandatory roles, models and independent review, and project exceptions.” Adjust the link to the actual installed location. This provision does not alter host configuration or override native role instructions.

Follow applicable user, project and host instructions, their priority and actual permission limits. The main agent determines the scope and whether to delegate, passes required procedures and policies, and checks results. A subagent uses only its received scope and follows the applicable Batang delegation guidance and host limits. Existing model and role settings remain in effect; no profile or global setting is created automatically.

For delegation, pass the goal, applicable policy, authority, owned files, dependencies, completion criteria and required evidence, then check observable roles, document references, actions and results. Record unobservable internal receipt as unverified; do not require an ACK or byte-level proof. Map responsibilities to available host roles and distinguish requested and actual models and tools. A skill selection grants no additional permission. Do not automatically extend Batang-specific procedures to a later unrelated task.

Review and verification follow the [work contract](../skills/batang/components/madi/references/workflow-contract.md), including approval and registration before new or strengthened test conditions are applied, and the applicable project requirements. If a mandatory model or review cannot be performed or verified, record the affected step as blocked. When independent review is required or performed, preserve evidence of independence, the fixed target and actual result.
