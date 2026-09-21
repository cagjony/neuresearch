#!/usr/bin/env python3
"""
flatten_fields.py — turn Word field codes into the plain text they display.

    python flatten_fields.py in.docx out.docx

A Zotero citation is a Word FIELD: a begin marker, an <w:instrText> carrying a
large CSL-JSON blob, a separator, the runs that are actually shown, and an end
marker. The blob makes the document depend on the author's Zotero library, and
it inflates every word count (one 129-word paragraph measured 909).

This keeps the displayed runs and removes the machinery around them. The result
is self-contained and safe to edit, and the citation text no longer updates from
Zotero — which is why this writes a NEW file and never touches the input.

The transform must not change one visible character, so it verifies exactly
that: it compares the concatenated <w:t> text before and after, and refuses to
write if they differ.
Requires: Python 3.10+ (stdlib only).
"""
from __future__ import annotations

import html
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

RUN = re.compile(r'<w:r(?:\s[^>]*)?>.*?</w:r>', re.S)


def visible(xml: str) -> str:
    runs = re.findall(r'<w:t(?:\s[^>]*)?>(.*?)</w:t>', xml, re.S)
    return ''.join(html.unescape(re.sub(r'<[^>]+>', '', r)) for r in runs)


def flatten(doc: str) -> tuple[str, int, int]:
    # <w:fldSimple w:instr="...">runs</w:fldSimple> -> just the runs
    simple = len(re.findall(r'<w:fldSimple\b', doc))
    doc = re.sub(r'<w:fldSimple\b[^>]*>(.*?)</w:fldSimple>', r'\1', doc, flags=re.S)
    # drop the runs that hold the field machinery; keep the displayed ones
    dropped = 0

    def kill(m: re.Match) -> str:
        nonlocal dropped
        r = m.group(0)
        if '<w:fldChar' in r or '<w:instrText' in r:
            dropped += 1
            return ''
        return r

    doc = RUN.sub(kill, doc)
    return doc, simple, dropped


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if src.resolve() == dst.resolve():
        sys.exit('flatten_fields: refusing to overwrite the input')
    z = zipfile.ZipFile(src)
    out_parts = {}
    total_simple = total_dropped = 0
    for name in ('word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml'):
        if name not in z.namelist():
            continue
        before = z.read(name).decode('utf-8')
        after, s, d = flatten(before)
        if visible(before) != visible(after):
            sys.exit(f'flatten_fields: {name} — visible text changed. Nothing written.')
        ET.fromstring(after.encode('utf-8'))
        out_parts[name] = after
        total_simple += s
        total_dropped += d
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zw:
        for it in z.infolist():
            zw.writestr(it, out_parts.get(it.filename) or z.read(it.filename))
    print(f'wrote {dst}')
    print(f'  field runs removed: {total_dropped}   fldSimple unwrapped: {total_simple}')
    print('  visible text verified identical')


if __name__ == '__main__':
    main()
