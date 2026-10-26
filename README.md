> AI agents: read [AGENTS.md](AGENTS.md) first. [Korean](README.ko.md)

# Batang

Batang organizes selected material into source-linked knowledge and puts that knowledge to work in software, documentation, and diagrams.

I wanted one workflow from gathering knowledge to making what I need. I designed it to grow by keeping source notes, tools, and work procedures distinct.

I did not write the code or documentation myself. I shaped the features and scope through conversations with AI, then iterated on implementation and verification.

## Get started

The supported environment for 0.0.9 is **Codex on macOS ARM64**. The required software is listed below.

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
| “Use the notes I selected to update my decision note, with links to the source passages.” | A scoped update that links the requested note to its sources. |
| “What did I decide about this topic? Compare the notes I selected and explain how they relate.” | A comparison of related notes that explains the decisions and their sources. |
| “Use these notes to draft a short guide and make a diagram of the workflow.” | A guide and requested diagram based on the selected notes. |

## Batang's components

| Component | What it does |
|---|---|
| [`Gadak`](skills/batang/components/gadak/workflow.md) | Sets the source, tool paths, and project policies for the work. |
| [`Naru`](skills/batang/components/naru/workflow.md) | Connects Codex request handling to Batang's work procedures and prepared tools. |
| [`Dure`](skills/batang/components/dure/workflow.md) | Defines allowed targets and the checks, backup, and recovery conditions before a change. |
| [`Madi`](skills/batang/components/madi/workflow.md) | Plans and creates development, documentation, and diagram work, then connects an independent review. |
| [`Supul`](skills/batang/components/supul/workflow.md) | Adds selected material, retrieves knowledge, and handles corrections. |

`Galpi`, `Gori`, and `Bogi` are responsibilities within `Supul`.

| Component | What it does |
|---|---|
| [`Galpi`](skills/batang/components/supul/galpi/workflow.md) | Reads selected notes and keeps their sources clear. |
| [`Gori`](skills/batang/components/supul/gori/workflow.md) | Shows relationships between notes and concepts. |
| [`Bogi`](skills/batang/components/supul/bogi/workflow.md) | Creates explanations and diagrams when requested. |

These are responsibilities within one Batang skill. The host AI connects the relevant procedures and existing tools for each request.

Batang answers from the notes you select. Relationship maps and diagrams are supporting material that helps explain them.

## Reading and changes

- Batang reads only the notes and permitted sources you select for the task.
- It saves nothing from a conversation automatically.
- When you ask for an update, it changes only the target you specify and makes a backup before editing an existing note.

For details, see [Reading and saving notes](skills/batang/references/source-access.md) and [Note format and sources](skills/batang/references/knowledge-contract.md).

## License

[MIT](LICENSE) © 2026 EPKO · [Third-party notices](THIRD_PARTY.md)
