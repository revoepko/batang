> AI agents: read [AGENTS.md](AGENTS.md) first. [Korean](README.ko.md)

# Batang

Batang helps you organize selected notes with links to their sources, then find and use that knowledge in software, documents, and diagrams.

[Release notes](RELEASE.md)

## Get started

The supported environment is **Codex on macOS ARM64**. The required software is listed below.

| Required software | Purpose |
|---|---|
| Obsidian | Storing and managing your notes. |
| Graphify | Organizing relationships between notes and concepts. |
| Archify | Creating an explanation or diagram when you request one. |

Graphify uses Python, and Archify uses Node.js as its runtime. See [Third-party notices](THIRD_PARTY.md) for versions and details.

Clone the repository and enter its folder:

```sh
git clone https://github.com/revoepko/batang.git
cd batang
```

In this folder, open Codex and ask:

```text
Please install Batang according to this folder's AGENTS.md.
```

Codex records the confirmed paths in the target project's `AGENTS.md` and verifies the single Batang skill registration.

## Try it with natural language

| Example request | Expected result |
|---|---|
| “Make an explanation page where I can select topics to explore this content.” | A page that changes the content in the same area below the selection buttons. |
| “Use these notes to update decision.md with my decision and its sources.” | A scoped update that links the requested note to its sources. |
| “Find and compare the decisions I made about this topic in these notes.” | A comparison of related notes that explains the decisions and their sources. |
| “Make a short guide and a workflow diagram from these notes.” | A guide and requested diagram based on the selected notes. |

## Batang's components

| Component | What it does |
|---|---|
| [`Gadak`](skills/batang/components/gadak/workflow.md) | Checks which notes and tools to use and whether the project is ready. |
| [`Naru`](skills/batang/components/naru/workflow.md) | Chooses the knowledge, development, document, or diagram path for your request. |
| [`Dure`](skills/batang/components/dure/workflow.md) | Checks which files may change and the backup and recovery conditions first. |
| [`Madi`](skills/batang/components/madi/workflow.md) | Plans and creates development, document, or diagram work, then has another reviewer check it. |
| [`Supul`](skills/batang/components/supul/workflow.md) | On request, saves selected material to notes, finds information, and helps correct it. |

`Galpi`, `Gori`, and `Bogi` are responsibilities within `Supul`.

| Component | What it does |
|---|---|
| [`Galpi`](skills/batang/components/supul/galpi/workflow.md) | Reads selected notes and keeps their sources clear. |
| [`Gori`](skills/batang/components/supul/gori/workflow.md) | Shows relationships between notes and concepts. |
| [`Bogi`](skills/batang/components/supul/bogi/workflow.md) | Creates explanations and diagrams when requested. |

These components belong to one Batang skill. The host AI connects the relevant procedures and tools you have prepared, and carries out the work.

Batang answers from the notes you select. Relationship maps and diagrams are supporting material that helps explain them.

## Reading and changes

- Batang reads only the notes and permitted sources you select for the task.
- It saves nothing from a conversation automatically.
- When you ask for an update, it changes only the target you specify and makes a backup before editing an existing note.

For details, see [Reading and saving notes](skills/batang/references/source-access.md) and [Note format and sources](skills/batang/references/knowledge-contract.md).

You can also import notes written elsewhere. Batang converts copies of the selected notes to its format, records their sources, and leaves the originals unchanged. Notes that cannot be converted are not registered, and Batang tells you why. See [import guidance](skills/batang/references/import.md).

You can give notes alternative names with `aliases`. The AI uses aliases of selected notes as clues to find related content. See [relationship guidance](skills/batang/components/supul/gori/workflow.md).

## License

[MIT](LICENSE) © 2026 EPKO · [Third-party notices](THIRD_PARTY.md)
