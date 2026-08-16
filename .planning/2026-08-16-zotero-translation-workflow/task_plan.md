# Task Plan: Zotero-backed bilingual PDF workflow

## Goal

Make long-book translation reliably finalize into a navigable bilingual PDF, then prepare a safe, reviewable Zotero storage and reading-queue workflow without losing existing content.

## Current Phase

Phase 5

## Phases

### Phase 1: Discover current translation and Zotero state

- [x] Confirm the existing long-book runner and finalization gap.
- [x] Inspect the local Zotero data directory, database shape, storage layout, and any safe integration surface.
- [x] Record the exact boundaries between preview/audit and destructive library changes.
- **Status:** complete

### Phase 2: Design the durable workflow

- [x] Define output lifecycle, numbering, deterministic filenames, and batch ordering.
- [x] Define the Zotero collection/tag/item decision flow and no-loss migration rules.
- [x] Decide which parts belong in the BabelDOC repo and which belong in the personal skill.
- **Status:** complete

### Phase 3: Implement local translation finalization

- [x] Make successful chunk processing explicitly merge and repair navigation.
- [x] Keep intermediate chunk output recoverable until verification and handoff succeed.
- [x] Add a machine-readable job manifest/report and tests for completion behavior.
- **Status:** complete

### Phase 4: Implement Zotero preview and controlled ingestion

- [x] Build an audit/preview command that never modifies Zotero.
- [x] Build a confirmation-gated ingest command with item-or-collection choice and at most five tags.
- [x] Apply the approved, additive collection hierarchy and dynamic Saved Searches.
- [x] Do not move, delete, or deduplicate existing Zotero attachments.
- **Status:** complete

### Phase 5: Extend the personal skill and verify

- [x] Update `babeldoc-bilingual-pdf` with the new finalization and Zotero decision workflow.
- [x] Validate scripts against fixture data; inspect any generated report.
- [x] Verify the reorganized library through Zotero UI and the read-only Local API.
- **Status:** complete for the no-loss structural pass

## Key Questions

1. Which collection hierarchy and sequence format best supports a mixed existing library and a future reading queue?
2. Can Zotero's local database be safely inspected read-only while the app is closed or via a non-mutating copy?
3. Which supported API/CLI integration can add attachments and tags without direct database writes?

## Decisions Made

| Decision | Rationale |
| --- | --- |
| Do not modify the existing Zotero library during discovery | The user requires no content loss; attachment moves, deduplication, and collection changes need a reviewable preview and explicit approval. |
| Keep final user deliverable outside transient `output/chunks` | Chunk folders are resumable working state; final navigable dual PDFs need a stable library handoff path. |
| Keep the private BabelDOC config local | It contains private service configuration and must not enter code, logs, reports, or commits. |
| Use the running Zotero local API for read-only audit discovery | The verified local API can enumerate library structure without direct SQLite access. |
| Keep library reorganization additive in the first pass | New queue collections and tags can be added without moving/deleting existing records; any consolidation remains a separately approved migration batch. |
| Store reading order in a structured per-item field, not a unique tag | A queue number is ordering data. Putting it in `Extra` or a stable field avoids indefinitely growing the tag vocabulary. |
| Split Zotero management into a separate skill | The user will participate in audit/review. The translation skill only produces final navigable PDFs and a handoff manifest. |
| Final staging format is `output/final/<queue-id>--<book>/` | The stable sequence enables batch sorting and separates deliverables from resumable chunk outputs. |
| Use a separate `$zotero-library-curator` skill for library work | The PDF skill hands off final PDFs and evidence; the Zotero skill owns review gates and future attachment writes. |
| Reparent collections and add dynamic Saved Searches in an additive first batch | The user explicitly authorized automatic reorganization. The implementation preserves all items, tags, and attachment files. |

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| Plugin-management connector search is unavailable in this session | 1 | Continue with local Zotero discovery; do not claim a Zotero plugin is connected. |
| Broad finalization patch did not match `LOCAL_USAGE.md` context | 1 | Read the exact current sections and apply a narrower patch; no source files changed. |
| Shell could not resolve `mv` while cleaning generated fixture outputs | 1 | Use absolute `/bin/mv` after rechecking each exact test target. |
| Skill patch attempted delete-and-add for the same file | 1 | Replace the skeleton with one update operation, then add resources separately; no skill files changed. |
| Dynamic-view patch had a stale reference-document context line | 1 | Read the exact tag line and reapply a narrow patch; all intended changes then applied. |
