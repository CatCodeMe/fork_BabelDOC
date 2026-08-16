# Progress

- 2026-08-16: Created branch `codex/toc-layout-adapters-20260816` from local `main`.
- 2026-08-16: Inspected the B-tree source/output with PyMuPDF and the translation tracking file; root cause is pre-translation paragraph grouping, not LLM omission.
- 2026-08-16: Added the conservative generic detector, named `now-publishers` profile seam, CLI selection, and three unit tests; full test suite passes.
- 2026-08-16: Ran one-page parse-only and real translation validation for the affected NOW source. The parser produced one paragraph per TOC row and the clean dual PDF visibly preserves every entry's newline.
- 2026-08-16: Regenerated the complete 50-page B-tree first chunk into the non-overwriting `chunk-1-pages-1-50-repaired` directory. Both mono and dual PDFs contain 50 pages; the dual page 1 was rendered and visually verified.
