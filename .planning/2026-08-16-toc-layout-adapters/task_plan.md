# TOC layout adapters

## Goal

Repair collapsed table-of-contents entries in translated PDFs, beginning with the NOW Publishers B-tree source, with a general structural detector and an extensible source-adapter seam.

## Phases

1. [complete] Reproduce and locate the collapse before translation.
2. [complete] Add generic TOC row segmentation and adapter registry.
3. [complete] Add focused unit tests and run regression tests.
4. [complete] Regenerate the affected first chunk and visually verify its contents pages.
5. [complete] Document use, limitations, and follow-up publisher profiles.
6. [complete] Audit all current deliverable PDFs and turn the repair into a layered structural-recovery policy.
7. [complete] Correct grouped multi-line item handling; add conservative generic ordered/unordered list recovery.
8. [complete] Validate exact O'Reilly and Manning source/list pages, then regenerate only affected first chunks.
9. [complete] Keep one unambiguous navigable merged dual deliverable.
10. [complete] Add rendered-geometry overlap detection and structural-row typography fallback.
11. [complete] Repair Traction's ordinal-and-bullet contents rows and publish one navigable dual PDF.

## Guardrails

- Do not hard-code a PDF filename or publisher-specific coordinate map in the generic path.
- Preserve normal prose paragraphs; only split a run when multiple lines have a shared TOC-row signature.
- A publisher profile may only add a recognizer or policy override, never replace generic processing silently.
- Keep existing generated output immutable until a repaired artifact is verified.
- Generated bookmarks are a fallback only: they must be marked as generated and use high-confidence headings, never guessed chapter text.

## Errors encountered

- `references/local-workflow.md` is absent from this checkout although referenced by the translation skill; continued using the repository source and existing job artifacts.
- `pdftotext` is not installed; used PyMuPDF text extraction for source/output comparison.
- A first attempt to clear temporary test directories with `rm -rf` was blocked by the execution policy; used fresh uniquely named test directories instead.
- Manning exposes ordinary source lines, unlike O'Reilly's tightly stacked rows. Applying the O'Reilly visual-row recovery to Manning reordered overlapping glyph boxes and injected spurious letter fragments, so its profile now uses original source order.
- Manning's brief contents emits `appendix A` as a separate line immediately before the square-marker title; profile-specific grouping keeps those two source lines in one item.
