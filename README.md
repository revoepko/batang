> AI agents: read [AGENTS.md](AGENTS.md) first. [Korean](README.ko.md)

# Batang

Batang is an AI skill that finds what you need in the notes you choose, shows where it came from, and helps you use it in software, documents, and diagrams.
When you import existing notes, the originals stay untouched and Batang works on copies.

[Release notes](RELEASE.md)

## Get started

Use Codex CLI or the ChatGPT app on macOS ARM64.
Keep your notes in an [Obsidian](https://obsidian.md/download) vault.

The basic lookup tool for finding and reading notes runs on the Python standard library and needs neither Graphify nor Archify.
Organizing relationships between notes needs [Graphify](https://github.com/Graphify-Labs/graphify) (Python), and creating explanatory diagrams needs [Archify](https://github.com/tt-a1i/archify) (Node.js).
If they are missing, you can ask your AI to help install them. Checked versions are listed in [Third-party notices](THIRD_PARTY.md).

Clone the repository and open your AI tool in its folder:

```sh
git clone https://github.com/revoepko/batang.git
cd batang
```

Ask it to install Batang:

```text
Please install Batang according to this folder's AGENTS.md.
```

The AI confirms the project folder you work in and the vault where you keep notes, and asks if they are not yet decided. They need not be the same folder.
Existing settings and skill registrations are kept; only the settings you approve are added. See the [Codex guide](skills/batang/references/hosts/codex.md) for details.

## Start with existing notes

1. **Choose the notes to use.**
   Tell the AI which notes in your vault or folder to use with Batang. Notes you do not choose are not imported.

2. **Import copies.**
   Batang does not modify the originals. It prepares copies and records their sources.
   If a note has an unsupported format or needs review, Batang holds it and tells you.

3. **Register them in the note list.**
   Batang registers the prepared copies in the note list (for example, `ACTIVE.md`) and checks and reports whether each note was registered. Preparing copies and registering them are separate steps.
   Regular note search covers only notes in this list that are chosen for the current task and permitted for reading. It does not search your whole vault on its own.

4. **Ask.**
   Invoke Batang as shown in [Making requests](#making-requests) and ask what you want to find.

Notes already in Batang's format can be registered directly after a check. If you are starting fresh, you can prepare an empty vault.
See the [import guide](skills/batang/references/import.md) for what each step supports.

## Making requests

- Codex CLI: start your request with `$batang`.
- ChatGPT app: type `@` and select the Batang skill.

Batang applies only to the task you invoke it for and its follow-ups. It does not apply to other tasks automatically, and your existing AI instructions and roles stay in place.

| Example request | Expected result |
|---|---|
| "Import the notes in this folder into Batang." | Imports copies of the chosen notes and reports the registration result for each note. |
| "Find and compare what was decided about the caching strategy in these notes." | Compares the relevant notes and reports the decisions and evidence with sources. Distinguishes a later decision that replaced an earlier one from decisions that conflict. |
| "Using these notes, summarize the decisions in decision.md and include the sources." | Changes only the requested file and links the sources used. |
| "Create a short guide and a workflow diagram from these notes." | Creates a guide and a diagram based on the chosen notes. |

Batang answers from the notes you chose. If sources conflict or it cannot confirm that something still applies, it tells you so. Relationship maps and diagrams are supporting material.

## Reading and saving

- Batang reads only the chosen notes and permitted sources. It does not save conversations automatically.
- When you ask it to save, it changes only the specified target and backs up an existing note before editing it.
- You can edit imported copies in Obsidian. To keep finding them with Batang, keep the Batang properties (frontmatter) at the top in a valid format.
- Relationships between notes are organized only when you ask. A link alone does not confirm a relationship, and "no relationship" is a possible result. Diagrams are created only on request.

## Troubleshooting

- **What I'm looking for doesn't show up.** Check that the note is in the note list, chosen for this search, and permitted for reading. Regular note search does not automatically look beyond that scope.
- **Some search results are missing.** When selected notes have format or access problems, the result may include the confirmed failed paths and reasons alongside valid results. A partial result does not mean the search is complete or that nothing was found, so review the omissions with your AI. A global scope or active-list error may not reveal a path.
  An ordinary Markdown note in a supported format can be imported as a copy, but importing does not automatically repair damaged Batang properties. To search without that note, leave it out of this search.

For details, see the [query guide](skills/batang/references/query.md), [reading and saving notes](skills/batang/references/source-access.md), and the [relationship guide](skills/batang/components/supul/gori/workflow.md). Internal components and procedures are described in the [skill guide](skills/batang/SKILL.md).

## License

[MIT](LICENSE) © 2026 EPKO · [Third-party notices](THIRD_PARTY.md)
