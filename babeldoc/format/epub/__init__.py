"""EPUB-specific support for BabelDOC.

The PDF pipeline spends roughly 40% of its work recovering structure
(page layout, tables, paragraphs, styles, typesetting) from a format that
does not have any. EPUB already carries that structure, so this package works
directly on the XHTML DOM instead of building a layout intermediate
representation.

Layers, from the bottom up:

``archive``
    Open the ZIP container, resolve ``container.xml`` -> OPF -> spine, expose
    reading-order XHTML documents as parsed trees.
``style_profile``
    Work out what each CSS class *means* (heading / body line / page number /
    code / caption) by combining the stylesheet with corpus statistics.
``blocks``
    Flatten a document into an ordered stream of block elements annotated with
    their inferred role.
``normalize``
    Repair the damage done by PDF->EPUB reflow: typeset lines that were split
    into separate ``<p>`` elements, hyphenation across those splits, print page
    numbers, inline-code spans, and literal list markers.
``segment``
    Turn normalized blocks into translatable segments that carry references
    back to their text nodes, so translations can be written in place.
"""

from babeldoc.format.epub.archive import EpubArchive
from babeldoc.format.epub.archive import EpubDocument
from babeldoc.format.epub.archive import ManifestItem

__all__ = [
    "EpubArchive",
    "EpubDocument",
    "ManifestItem",
]
