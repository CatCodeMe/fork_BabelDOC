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
