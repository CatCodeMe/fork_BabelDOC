# Table-of-contents layout adapters

## Why this exists

PDF layout detection can return a whole contents column as one text block. If that
block reaches translation intact, the translated text is typeset as one paragraph
and the source entry boundaries disappear. This is a document-structure problem,
not a prompt or target-language problem.

## Default strategy

`--toc-layout-adapter auto` is enabled by default. Before translation it splits a
text block only when it contains a consecutive run of rows that all have:

1. a numbered section prefix such as `2` or `2.4`;
2. a terminal one-to-four digit page number; and
3. the same right edge for that page number (within 12 PDF points).

The third condition prevents a normal paragraph containing citations or years
from being split line-by-line. Each accepted row becomes one translation unit,
which retains its own original bounding box during Chinese typesetting.

## Profiles and extension policy

The profile values are `auto`, `generic`, `now-publishers`, and `off`.
`now-publishers` currently uses the proven generic numbered-row rule for the
Foundations and Trends/NOW source; it is named so a later publisher-specific
tolerance or row recognizer has a stable, explicit home.

Add an adapter only after saving a representative source PDF and a failing output
page. A profile may tune row recognition, minimum run length, or alignment
tolerance. It must not depend on a source filename or fixed page coordinates.
Keep `auto` conservative and leave it as the default; use a profile when a
publisher has a repeatable structure that the generic signature cannot capture.

## Current boundary

This recognizes numbered, right-aligned-page TOCs. Unnumbered front matter,
two-column rows whose page number is a separate detected line, and image-only
contents pages need evidence-driven additional recognizers. The parser preserves
the source-side structure; it does not reconstruct target-side PDF links.
