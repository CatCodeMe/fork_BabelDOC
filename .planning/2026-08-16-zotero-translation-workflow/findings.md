# Findings: Zotero-backed bilingual PDF workflow

## Requirements

- Ensure completed chunk translations proceed to merged outputs and navigable dual PDFs.
- Avoid retaining long-lived final output inside the chunk working tree.
- Add final translated PDFs to Zotero, either under an existing parent item or a selected collection, after asking the user for the destination.
- Add no more than five tags automatically.
- Audit and improve the current Zotero attachment/category organization without losing content.
- Add a durable reading-order identifier and support batch translation ordering.
- Extend the personal `babeldoc-bilingual-pdf` skill.

## Research Findings

- `translate-chunks.zsh` currently has separate `prepare`, `parallel`, and `merge` modes. Its `parallel` mode completes chunks but does not invoke merge or navigation repair.
- `repair_navigation.py` produces a sibling navigable dual PDF by copying TOC and numeric internal links from the source to the original/left half of the dual output.
- The local Zotero data locations found are `/Users/hulj/Library/Application Support/Zotero` and `/Users/hulj/Zotero`; Zotero.app is installed.
- No `zotero` command-line executable is on PATH.
- Zotero is currently running with profile `bhr2n6fv.default`; do not read or write its live SQLite database directly.
- The first local-API probe did not execute because unquoted `?limit=1` was treated as a zsh glob. Retry with a quoted URL rather than repeating the malformed command.
- The active data directory is `/Users/hulj/Zotero`, containing `zotero.sqlite` (about 37 MB) and `storage/` (about 2.4 GB).
- Zotero's local API is available on `127.0.0.1:23119`; a quoted read-only collections request succeeded. This is the preferred audit surface while the app is running.
- Official Zotero documentation confirms the local API accepts only `GET` today. The supported local write surface is Zotero's privileged JavaScript API; direct SQLite writes are fragile and excluded.
- The library has 21 top-level collections, 81 tags, 298 top-level items, and 325 attachments. Current organization is largely flat, with no top-level collection containing a child collection.
- Existing reading-state tags already use `/unread` (69 items) and `/reading` (9 items). New workflow tags should reuse those semantics rather than introduce competing unread/reading labels.
- The top-level collection list includes overlapping broad topics and states (for example `book`, `paper`, `TODO`, `00_最近收集`) but no explicit ordered reading queue.
- A two-page PyMuPDF fixture confirmed the new finalization path creates an incremented queue directory, page-count-matched navigable PDF, preserved TOC/internal link, and `handoff.json`.
- The standalone `zotero-library-curator` skill now validates, audits through the read-only Local API, searches candidate parent items, generates a plan with a five-tag cap, and refuses to generate writable JavaScript without `--confirmed`.
- A completed-chunk `run` fixture also confirmed automatic finalization, not only direct `merge`: completed chunks were skipped, then the final navigable PDF and report were created.
- The active Zotero configuration uses WebDAV attachment sync. A read-only sample contains `imported_file` attachments (including PDFs) alongside imported URLs, so the local data directory is not metadata-only; it holds managed attachment files/cache as well.
- Classification must operate on Zotero collections, item memberships, tags, and fields. The `storage/<attachment-key>/` directories are Zotero-managed physical storage and must never be manually reorganized to express categories.
- Zotero Collections are static item memberships; Saved Searches are the continuously updated dynamic view mechanism. A Saved Search with `Tag is /unread` and `Item Type is not attachment` supplies the requested automatic unread view without file copies or synchronization scripts.
- The approved structural pass created six top-level parent collections, four reading-queue child collections, and reparented 21 existing collections. It created three dynamic Saved Searches: `📥 未读`, `📖 阅读中`, and `🈶 待整理双语版`.
- Post-change Local API audit: 31 collections, 81 tags, and 325 attachments. The tag and attachment counts are unchanged from the pre-change audit; no file-system move was performed.

## Technical Decisions

| Decision | Rationale |
| --- | --- |
| Separate `finalize` from raw `merge` | A deterministic finalizer can merge, repair navigation, validate, and create a handoff manifest without hiding those steps inside parallel execution. |
| Ask before destination choice | Existing item attachment versus new/selected collection is a semantic user decision; it cannot be guessed safely. |
| Make audit read-only first | Directly changing Zotero's existing collections/attachments risks data loss and hides ambiguous duplicates. |
| Never mutate Zotero's live SQLite database | Use an API or a closed-app database copy for reads; use an approved Zotero-facing write path only after preview and confirmation. |
| Reuse `/unread` and `/reading` | The current library already uses them at meaningful scale; use new tags only for provenance/language/batch metadata. |
| Create a dedicated Zotero-library skill | Keep library access, review gates, and future write capability out of the PDF translation skill. |
| Auto-finalize only whole-book run modes | `run`, `parallel`, and `all` finalize; `one` remains a targeted retry that requires an explicit later merge. |
| Write through Zotero's privileged JS API only after plan approval | It imports a stored attachment and never writes the local database directly. |
| Preserve legacy tags for the structural pass | Existing tag meanings cannot safely be inferred. A tag consolidation plan must be a separate, reviewable batch. |
| Model WebDAV as attachment sync, not a category filesystem | Metadata/category changes are logical Zotero changes; avoid file-system moves that would break managed attachments or sync. |
| Use Saved Searches for unread/reading dashboards | Dynamic criteria views avoid manually synchronizing static collections to tags. |

## Resources

- Local tool root: `/Users/hulj/tools_wp/babeldoc`
- Personal skill: `/Users/hulj/.codex/skills/babeldoc-bilingual-pdf`
- Zotero profile data: `/Users/hulj/Library/Application Support/Zotero`

## Visual/Browser Findings

- None yet.
