# TOC layout adapters

## Goal

Repair collapsed table-of-contents entries in translated PDFs, beginning with the NOW Publishers B-tree source, with a general structural detector and an extensible source-adapter seam.

## Phases

1. [complete] Reproduce and locate the collapse before translation.
2. [complete] Add generic TOC row segmentation and adapter registry.
3. [complete] Add focused unit tests and run regression tests.
4. [complete] Regenerate the affected first chunk and visually verify its contents pages.
5. [complete] Document use, limitations, and follow-up publisher profiles.

## Guardrails

- Do not hard-code a PDF filename or publisher-specific coordinate map in the generic path.
- Preserve normal prose paragraphs; only split a run when multiple lines have a shared TOC-row signature.
- A publisher profile may only add a recognizer or policy override, never replace generic processing silently.
- Keep existing generated output immutable until a repaired artifact is verified.

## Errors encountered

- `references/local-workflow.md` is absent from this checkout although referenced by the translation skill; continued using the repository source and existing job artifacts.
- `pdftotext` is not installed; used PyMuPDF text extraction for source/output comparison.
- A first attempt to clear temporary test directories with `rm -rf` was blocked by the execution policy; used fresh uniquely named test directories instead.
