# Release notes

[한국어](RELEASE.ko.md)

## 0.1.1-b (in development)

### Changed

- Reduced the cost of checking duplicate paths in the ACTIVE list while preserving the existing path order and error handling.
- The read-only query session provides scoped search, passage, relationship, and review-context lookups. Within the same process and model context it can refer to passages after they are received and acknowledged; a new context requires the needed evidence again. [Query guidance](skills/batang/references/query.md)
- Routine knowledge work uses one performer with the necessary tools by default, while honoring explicit delegation and mandatory host or project roles and review. Where the host permits, an assigned planner directly manages delegated work and integrates its results. [Delegation guidance](skills/batang/references/delegation.md)
- Relationship updates compare permitted existing documents and distinguish the type, direction, conditions and evidence of relationships between documents. The relationship review reports partial comparisons and deferred decisions.
- When a document or its evidence changes, affected relationships are reviewed again, with independent supporting evidence kept distinct. A document node marked `current` does not mean relationship quality has been reviewed completely.
- Accept or defer individual relationships between the same documents. A deferred existing relationship is excluded from confirmed results while its supporting history is preserved, and can be accepted again after reviewing current evidence.

### Compatibility

- Existing relationship data is not converted automatically. The new relationship format requires a separately approved conversion and is projected through Batang rather than passed directly to existing Graphify commands. [Relationship guidance](skills/batang/components/supul/gori/workflow.md)

## 0.1.1-a

### Changed

- Limited the supported hosts to Codex CLI and the ChatGPT app.
- Removed Claude-specific guidance and configuration examples.

## 0.1.1

### Changed

- Batang now applies only to tasks where you explicitly invoke it and follow-up requests for those tasks.
- Updated shared procedures to follow applicable user, project and host rules, and added Codex and Claude Code host guidance.
- Clarified delegation, independent review and evidence handoff within the single skill, while preserving personal host settings and project requirements.
- Guidance explains how to use the same Batang skill in Codex and Claude Code and continue work from shared material and work records.
- Direct Markdown lookup needs neither Graphify nor Archify. Graphify is used for relationship work and approved refreshes; Archify is used for requested visualizations.
- When a graph is missing, outdated or incomplete, Batang checks the current Markdown to answer and reports the state of the relationship data.
- Batang checks when and under what conditions sources apply, including conflicting evidence.
- Valid preparation checks are reused when the target, settings, versions, permissions and Batang files remain the same. Relevant changes, errors or uncertain conditions trigger a check of the affected parts.

### Compatibility

- If an existing installation has instructions to always use Batang, update them to apply only to tasks where you invoke Batang. Keep other AI instructions and agent roles unchanged.

## 0.1.0-b

### Changed

- New managed documents use short, clear topic filenames without IDs. The internal `batang_id` remains; add the subject or target to distinguish a collision. Existing documents are renamed only when explicitly requested. [Naming guidance](skills/batang/references/knowledge-contract.md#관리-문서-이름)

## 0.1.0-a

### Changed

- Read note content and supported properties again after editing in Obsidian. Additional properties are preserved; unsupported structures are kept for review with an explanation.
- Import selected notes within the same vault. Originals remain unchanged, and Batang checks copied links and the status of each selected item.
- Check registered notes and their relationship updates together. Notes remain readable if a relationship update cannot be completed, and the update can be checked again on a later related request.
- Sources for newly imported notes use a locally resolvable reference in shared notes instead of the original folder's absolute path. Existing source records remain unchanged.
- The explanation panel example now offers an all-content view, full printing, and links to individual items, with a more compact layout on small screens.

### Compatibility

- Open notes using the new source references and additional properties with Batang 0.1.0-a. Existing documents are not converted automatically.

## 0.1.0

### Added

- Import selected notes as independent copies, preserving originals and recording their sources. Notes without metadata or using the supported YAML subset can be converted. Unsupported attributes or structures are held for review. [Import guidance](skills/batang/references/import.md)
- Give notes alternative names with `aliases`.
- Eligible empty temporary files and folders can be cleaned up. Automatic cleanup is withheld by default. The host cleans up only while it holds a lock that prevents concurrent access by other operations following the same locking rules. The lock does not guarantee exclusion of apps that do not cooperate. Content is preserved if saving the local file fails or its outcome is uncertain. [File access](skills/batang/references/source-access.md)

### Changed

- Bogi’s [reusable HTML explanation panel example](skills/batang/components/supul/bogi/assets/explanation-panel.html) lets readers choose an item and see its content in the same place. Replace the example with content and sources you are allowed to use. On desktop and mobile, it avoids forced scrolling, keeps conditions visible, and remains readable without JavaScript.
- When a recommended model is unavailable, guidance helps the AI coordinating the work choose a permitted alternative while respecting project requirements. [Workflow contract](skills/batang/components/madi/references/workflow-contract.md)
- Explore relationships using aliases of selected active notes. The AI matches aliases against those notes; automatic alias searches by Graphify itself are not guaranteed. [Relationship guidance](skills/batang/components/supul/gori/workflow.md)

### Compatibility

- Notes containing aliases can be read in Batang 0.1.0. Earlier versions cannot read them.
