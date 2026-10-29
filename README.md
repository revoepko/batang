> AI agents: read [AGENTS.md](AGENTS.md) first. [Korean](README.ko.md)

# Batang

Batang helps you organize selected notes with links to their sources, then find and use that knowledge in software, documents, and diagrams.

[Release notes](RELEASE.md)

## Get started

The supported environment is **Codex on macOS ARM64**. The required software is listed below.

| Required software | Purpose |
|---|---|
| [Obsidian](https://obsidian.md/download) | Storing and managing your notes. |
| [Graphify](https://github.com/Graphify-Labs/graphify) | Organizing relationships between notes and concepts. |
| [Archify](https://github.com/tt-a1i/archify) | Creating an explanation or diagram when you request one. |

Graphify uses Python, and Archify uses Node.js as its runtime. If a required tool is missing, you can ask Codex to help install it. See [Third-party notices](THIRD_PARTY.md) for the versions checked and more details.

Clone the repository and enter its folder:

```sh
git clone https://github.com/revoepko/batang.git
cd batang
```

In this folder, open Codex and ask:

```text
Please install Batang according to this folder's AGENTS.md.
```

Codex confirms the project folder where you will use Batang and the vault where you keep your notes. The project is the folder where you work with Codex; it does not have to be the vault. Codex records confirmed settings in the project's `AGENTS.md` and preserves existing settings and skill registrations.

Tell Codex whether you want to import existing notes and which notes to use. You can also prepare an empty vault to start fresh. Imported notes are copied, leaving the originals unchanged.

## Try it with natural language

| Example request | Expected result |
|---|---|
| “Import the notes in this folder into Batang.” | Imports copies of the selected notes and checks their links. |
| “Find related information in the imported notes.” | Explores notes and relationships, then identifies the sources. |
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

You can also import notes written elsewhere. Batang registers copies of the selected notes and their sources, then checks the links between copies. It leaves the originals unchanged. If an attribute or link needs review, it is preserved and Batang explains why. See [import guidance](skills/batang/references/import.md).

You can edit imported note content and properties in Obsidian. If Batang cannot update the relationship data after saving a note, the note remains readable and Batang reports that the update is pending.

You can give notes alternative names with `aliases`. The AI uses aliases of selected notes as clues to find related content. See [relationship guidance](skills/batang/components/supul/gori/workflow.md).

## License

[MIT](LICENSE) © 2026 EPKO · [Third-party notices](THIRD_PARTY.md)
