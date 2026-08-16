# Findings

- The B-tree contents page is source PDF page 1 of `work/input-chunks/2010_Modern_B-Tree_Techniques/chunk-001-pages-1-50.pdf`.
- The generated mono PDF turns several source TOC rows into a single translated paragraph (for example, `1.1` through `1.4`), so the failure occurs upstream of the language model's formatting.
- `translate_tracking.json` records the same evidence: one input unit contains six section entries in sequence and the model returns one sequence.
- `ParagraphFinder._group_characters_into_paragraphs` groups all characters assigned to one layout region. Its line splitter retains the source lines internally, but `process_independent_paragraphs` only splits dotted-leader or short-line cases, so this source's aligned-number TOC rows stay in one paragraph.
- Generic repair: recognize a consecutive run of at least two numbered/title/page-number rows with a consistently aligned terminal page number, then make one `PdfParagraph` per source line before translation.
- Extensibility: use a registry of named `TocLayoutAdapter` policies. The default generic detector is always attempted; named profiles may tune recognition or opt into a known source pattern. Source selection must be explicit/configurable rather than inferred from a filename.
- O'Reilly v7 confirms that row segmentation is correct but does not alone ensure visual separation: translated CJK glyphs can exceed the original Latin single-row boxes. The final rendered glyph geometry must be checked for overlaps.
