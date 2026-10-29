# Release notes

[한국어](RELEASE.ko.md)

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
