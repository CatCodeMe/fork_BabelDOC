# Progress

- 2026-08-16: Created branch `codex/toc-layout-adapters-20260816` from local `main`.
- 2026-08-16: Inspected the B-tree source/output with PyMuPDF and the translation tracking file; root cause is pre-translation paragraph grouping, not LLM omission.
- 2026-08-16: Added the conservative generic detector, named `now-publishers` profile seam, CLI selection, and three unit tests; full test suite passes.
- 2026-08-16: Ran one-page parse-only and real translation validation for the affected NOW source. The parser produced one paragraph per TOC row and the clean dual PDF visibly preserves every entry's newline.
- 2026-08-16: Regenerated the complete 50-page B-tree first chunk into the non-overwriting `chunk-1-pages-1-50-repaired` directory. Both mono and dual PDFs contain 50 pages; the dual page 1 was rendered and visually verified.
- 2026-08-16: Expanded the scope from one publisher to a three-layer recovery strategy: known-publisher profiles, conservative generic TOC/list row splitting, and generated sidebar navigation when a source has no usable TOC.
- 2026-08-16: Added a read-only tracker corpus audit tool covering all saved `work/chunks/**/translate_tracking.json` files.
- 2026-08-16: Fixed the adapter implementation so wrapped O'Reilly and Manning entries remain one translation unit rather than being re-split line-by-line; added a conservative automatic list splitter for proved three-item lists.
- 2026-08-16: Recovered vertically stacked rows that the full-page layout model had collapsed into one oversized PDF line. Full 50-page O'Reilly retranslation now preserves one Chinese row per TOC entry when rendered.
- 2026-08-16: Added a final-PDF line-overlap detector and an 82% scale cap for structural TOC/list rows. On the O'Reilly contents page, detected right-side overlaps decreased from 17 to 3; the remaining hits include page-footer glyphs.
# 2026-08-16 Manning targeted repair

- Reprocessed only `Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_` chunk 1 (pages 1-50) using the validated `manning` adapter.
- Added profile-specific row labels/type caps, inverted-exclamation bullet handling, detached appendix-label grouping, and a regression test suite now containing 8 passing tests.
- v5 output: `output/chunks/Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_/chunk-1-pages-1-50-manning-repaired-v5/chunk-001-pages-1-50.no_watermark.zh-CN.dual.pdf`.
- Merged the repaired first chunk with the existing chunks 2-9. The final navigable dual PDF retains 123 bookmarks and 657 internal links; physical brief-contents page 8 has 22 destinations and formal-contents page 10 has 18.

# 2026-08-16 corpus audit

- Began a read-only audit of all existing `output/chunks` translations (seven book roots, 90 dual chunks). The structure audit script takes its output path as a positional argument; an initial `--output` invocation failed before it created any report or changed a PDF.
- Added `tools/audit_chunk_contents.py`, which selects one current deliverable per book and reports rendered right-half overlaps only on detected continuous contents pages. Initial audit: O'Reilly 59, Manning 1 decoration false positive, all other current books 0.
- O'Reilly v9 at a 0.70 profile-specific cap reduced the contents-page collision count to 53, but rendered page 19 still has adjacent long-row contact; starting a stricter 0.55-only retry.
- O'Reilly v10 at 0.55 reduced its 13 contents pages to 7 residual geometry hits. Rendered page 19 is readable with no adjacent long-row cover-up. Rebuilt the 1061-page merged/navigable dual PDF with only this first chunk replaced; it retains 486 bookmarks and 972 clickable internal links.
- Final canonical-PDF audit: zero contents collisions for Mathematics, B-tree, 2023 Data Structures, Inference Engineering, and graph-engineering; Manning 1 known chapter-decoration false positive; O'Reilly 7 residual hits to monitor, visually acceptable at the verified sample page.

# 2026-08-17 navigation alias repair

- User reported no sidebar outline in the O'Reilly final. The explicit `.dual.navigable.pdf` contained 486 bookmarks and 972 links, while the sibling `.dual.pdf` had none. The merge launcher now deletes the intermediate `.dual.pdf` after navigation repair and retains only the unambiguous navigable final.

# 2026-08-17 Traction repair

- Rendered source/output page 4 and inspected the tracker. Confirmed a pre-translation structural collapse of all 25 table-of-contents rows, not an LLM-only formatting issue.
- First Traction retry did not split because the title region was absent from the profile's page-text predicate. Debug `paragraph_finder.json` proves the row recognizer itself finds all 26 entries, so the retry will rely on its explicit 3+ row signature rather than that unreliable predicate.
- Debugging found the remaining failure: Traction's rows were already individual source lines, but the O'Reilly-only visual-row recovery had been applied to them and separated their title/page/bullet pieces. Limited that recovery to O'Reilly and made the complete Traction signature an automatic fallback.
- Verified the repair with 9 focused tests, a debug parse with 26 `traction_toc` rows, and a rendered clean dual page 4. Published the 36-page navigable final with three verified chapter bookmarks; moved obsolete non-navigable and intermediate outputs to `test-work/` so the book output root has only one dual PDF.
