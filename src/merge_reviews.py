#!/usr/bin/env python3
r"""
merge_reviews.py
================
Merge two independently-reviewed branches of the SAME .docx into one file.

Word's own "Combine Documents" is interactive, and LibreOffice's
`.uno:MergeDocuments` silently drops comments and tables (verified 2026-09-14 on
the DeepLINK drafts: 42 comments and one table lost, output identical to input).
So the merge is done here, on the XML, at paragraph granularity.

    python merge_reviews.py --base A.docx --other B.docx --out merged.docx \
                            [--report merge-report.md]

Both inputs must descend from one common draft. The merge is per top-level body
block, aligned on each block's BASE text (tracked changes rejected), so an
insertion by one reviewer never shifts the other's anchors:

  only --base edited it    -> take the base block   (its edits + comments ride along)
  only --other edited it   -> take the other block
  both edited the prose    -> take the base block, and REPORT the conflict; the
                              other side's version is never silently discarded
  present only in --other  -> insert it (this is how a reviewer's new table survives)

Every comment from --other is carried over regardless of who won the block. Its
author, initials and timestamp are preserved; its id is renumbered into a free
range. It is re-anchored to the whole block rather than the original character
span (run-splitting at arbitrary offsets is where this kind of tool corrupts a
file), and the words it was attached to are prepended to the body as
`[on: "..."]` so nothing about what it referred to is lost.

Report-only on the inputs: they are opened read-only and never written.
Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

BODY_BLOCK = ('w:p', 'w:tbl', 'w:sdt')


def read_part(z: zipfile.ZipFile, name: str) -> str | None:
    return z.read(name).decode('utf-8') if name in z.namelist() else None


def split_body(doc: str) -> tuple[str, list[str], str]:
    """Return (prefix, top-level body blocks, suffix). Balanced scan, so a w:p
    nested inside a w:tbl is never mistaken for a top-level block."""
    m = re.search(r'<w:body[^>]*>', doc)
    if not m:
        sys.exit('merge_reviews: no <w:body> — is this a Word document?')
    start, end = m.end(), doc.rindex('</w:body>')
    inner, blocks, pos = doc[start:end], [], 0
    while pos < len(inner):
        nxt = None
        for tag in BODY_BLOCK:
            hit = re.compile(rf'<{tag}(?:\s[^>]*)?(/?)>').search(inner, pos)
            if hit and (nxt is None or hit.start() < nxt[0].start()):
                nxt = (hit, tag)
        if nxt is None:
            break
        hit, tag = nxt
        if hit.group(1) == '/':                      # self-closing, e.g. <w:p/>
            blocks.append(inner[hit.start():hit.end()])
            pos = hit.end()
            continue
        depth, scan = 1, hit.end()
        pat = re.compile(rf'<(/?){tag}(?:\s[^>]*)?(/?)>')
        while depth and (mm := pat.search(inner, scan)):
            depth += -1 if mm.group(1) else (0 if mm.group(2) else 1)
            scan = mm.end()
        blocks.append(inner[hit.start():scan])
        pos = scan
    return doc[:start], blocks, doc[end:]


def base_text(block: str) -> str:
    """The block's text with tracked changes REJECTED — the common ancestor's
    wording, which is what two branches can actually be aligned on."""
    b = re.sub(r'<w:ins\b.*?</w:ins>', '', block, flags=re.S)
    b = b.replace('<w:delText', '<w:t').replace('</w:delText', '</w:t')
    runs = re.findall(r'<w:t[^>]*>(.*?)</w:t>', b, re.S)
    return html.unescape(re.sub(r'<[^>]+>', '', ''.join(runs))).strip()


def shown_text(block: str) -> str:
    runs = re.findall(r'<w:t[^>]*>(.*?)</w:t>', block, re.S)
    return html.unescape(re.sub(r'<[^>]+>', '', ''.join(runs))).strip()


def n_text_edits(block: str) -> int:
    return len(re.findall(r'<w:(?:ins|del)\s', block))


def comment_ids(block: str) -> list[str]:
    return re.findall(r'<w:commentRangeStart[^>]*w:id="(\d+)"', block)


def parse_comments(xml: str | None) -> dict[str, str]:
    """id -> the whole <w:comment> element."""
    if not xml:
        return {}
    out = {}
    for m in re.finditer(r'<w:comment\b[^>]*>.*?</w:comment>', xml, re.S):
        cid = re.search(r'w:id="(\d+)"', m.group(0))
        if cid:
            out[cid.group(1)] = m.group(0)
    return out


def anchor_span(doc: str, cid: str) -> str:
    a = re.search(rf'<w:commentRangeStart[^>]*w:id="{cid}"[^>]*/>', doc)
    b = re.search(rf'<w:commentRangeEnd[^>]*w:id="{cid}"[^>]*/>', doc)
    if not (a and b) or b.start() <= a.end():
        return ''
    return shown_text(doc[a.end():b.start()])


def retag_comment(elem: str, new_id: str, anchor: str) -> str:
    """Renumber a <w:comment> and prepend the words it was attached to."""
    elem = re.sub(r'(<w:comment\b[^>]*?)w:id="\d+"', rf'\1w:id="{new_id}"', elem, count=1)
    if not anchor:
        return elem
    quoted = html.escape(anchor if len(anchor) <= 160 else anchor[:160] + '…')
    note = (f'<w:p><w:r><w:rPr><w:i/></w:rPr>'
            f'<w:t xml:space="preserve">[on: "{quoted}"]</w:t></w:r></w:p>')
    i = elem.index('>') + 1
    return elem[:i] + note + elem[i:]


def anchor_block(block: str, cid: str) -> str:
    """Wrap a whole w:p in a comment range. Tables and anything else are left
    alone — a range that straddles a table is how Word files get corrupted."""
    if not block.startswith('<w:p'):
        return block
    start = f'<w:commentRangeStart w:id="{cid}"/>'
    end = (f'<w:commentRangeEnd w:id="{cid}"/>'
           f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
           f'<w:commentReference w:id="{cid}"/></w:r>')
    ppr = re.match(r'<w:p(?:\s[^>]*)?>(\s*<w:pPr>.*?</w:pPr>)?', block, re.S)
    at = ppr.end() if ppr else block.index('>') + 1
    return block[:at] + start + block[at:-len('</w:p>')] + end + '</w:p>'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True, help='branch that wins a prose conflict')
    ap.add_argument('--other', required=True, help='branch merged into it')
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', help='markdown merge report (default: <out>.merge-report.md)')
    a = ap.parse_args()

    base_p, other_p, out_p = Path(a.base), Path(a.other), Path(a.out)
    for p in (base_p, other_p):
        if not p.is_file():
            sys.exit(f'merge_reviews: not found: {p}')
    if out_p.resolve() in (base_p.resolve(), other_p.resolve()):
        sys.exit('merge_reviews: --out would overwrite an input. Refusing.')

    zb, zo = zipfile.ZipFile(base_p), zipfile.ZipFile(other_p)
    doc_b, doc_o = read_part(zb, 'word/document.xml'), read_part(zo, 'word/document.xml')
    cm_b, cm_o = read_part(zb, 'word/comments.xml'), read_part(zo, 'word/comments.xml')
    if cm_b is None:
        sys.exit('merge_reviews: --base has no comments part; nothing to merge into.')

    pre, bb, suf = split_body(doc_b)
    _, ob, _ = split_body(doc_o)
    cdefs_b, cdefs_o = parse_comments(cm_b), parse_comments(cm_o)

    next_id = max([int(i) for i in cdefs_b] + [0]) + 1000   # free range, no collisions
    sm = SequenceMatcher(None, [base_text(x) for x in bb],
                              [base_text(x) for x in ob], autojunk=False)

    merged: list[str] = []
    plan: list[tuple[str, int]] = []             # (comment id, index in `merged`)
    ported: list[tuple[str, str, str]] = []      # (new id, author, anchor text)
    conflicts, took_other, inserted = [], [], []

    def register(cid: str) -> str | None:
        """Give --other's comment a free id here. Returns the new id."""
        nonlocal next_id
        if cid not in cdefs_o:
            return None
        new = str(next_id); next_id += 1
        anchor = anchor_span(doc_o, cid)
        author = re.search(r'w:author="([^"]*)"', cdefs_o[cid])
        cdefs_b[new] = retag_comment(cdefs_o[cid], new, anchor)
        ported.append((new, author.group(1) if author else '?', anchor))
        return new

    def adopt(block_o: str) -> str:
        """Take a block FROM --other. Its comment anchors travel inside it, so
        renumber them in place; leaving the old ids would dangle, because their
        definitions live in the other file's comments.xml, not this one."""
        for cid in comment_ids(block_o):
            new = register(cid)
            if not new:
                continue
            for tag in ('commentRangeStart', 'commentRangeEnd', 'commentReference'):
                block_o = re.sub(rf'(<w:{tag}[^>]*w:id=")({cid})(")', rf'\g<1>{new}\g<3>',
                                 block_o)
        return block_o

    def schedule(block_o: str, idx: int) -> None:
        """Anchor --other's comments on this block to merged[idx] — recorded by
        INDEX, not looked up later by searching the assembled XML. A comment
        range can span two paragraphs, and searching for it after the fact is
        how anchors get lost."""
        for cid in comment_ids(block_o):
            new = register(cid)
            if new:
                plan.append((new, idx))

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                blk_b, blk_o = bb[i1 + k], ob[j1 + k]
                eb, eo = n_text_edits(blk_b), n_text_edits(blk_o)
                idx = len(merged)
                if eo and not eb:
                    took_other.append((i1 + k, base_text(blk_b)[:120]))
                    merged.append(adopt(blk_o))       # its own comments ride along
                    for cid in comment_ids(blk_b):    # the base also commented here
                        plan.append((cid, idx))
                    continue
                if eb and eo:
                    conflicts.append((i1 + k, base_text(blk_b)[:120],
                                      shown_text(blk_b)[:300], shown_text(blk_o)[:300]))
                merged.append(blk_b)
                schedule(blk_o, idx)
        elif tag == 'delete':
            merged.extend(bb[i1:i2])                  # base-only blocks stay
        elif tag == 'insert':
            for blk in ob[j1:j2]:
                # Keep an empty paragraph too when it carries a comment — that is
                # exactly where a reviewer parks "add a table here".
                if base_text(blk) or comment_ids(blk) or '<w:tbl' in blk or '<w:drawing' in blk:
                    inserted.append(('table' if blk.startswith('<w:tbl') else 'para',
                                     base_text(blk)[:120] or '(empty — carries a comment)'))
                    merged.append(adopt(blk))
        else:                                         # replace: base's wording wins
            conflicts.append((i1, base_text(bb[i1])[:120] if i2 > i1 else '',
                              ' / '.join(shown_text(x)[:150] for x in bb[i1:i2]),
                              ' / '.join(shown_text(x)[:150] for x in ob[j1:j2])))
            idx = len(merged)
            merged.extend(bb[i1:i2])
            if i2 > i1:
                for blk_o in ob[j1:j2]:
                    schedule(blk_o, idx)

    # ---- apply the anchor plan ---------------------------------------------
    def anchor_target(idx: int) -> int | None:
        """A comment range must not straddle a table. Walk back to a paragraph."""
        for n in range(idx, -1, -1):
            if merged[n].startswith('<w:p'):
                return n
        return None

    unanchored = []
    for cid, idx in plan:
        n = anchor_target(idx)
        if n is None:
            unanchored.append(cid); continue
        merged[n] = anchor_block(merged[n], cid)

    # ---- drop dangling anchors ---------------------------------------------
    # A comment range can start in one block and end in another. When only one of
    # those blocks came from --other, the far end keeps an id that means nothing
    # here. Word shows such a file as damaged, so strip every anchor whose comment
    # does not exist in this package.
    live = set(cdefs_b)
    stray = set()
    for n, blk in enumerate(merged):
        for tg in ('commentRangeStart', 'commentRangeEnd', 'commentReference'):
            for cid in re.findall(rf'<w:{tg}[^>]*w:id="(\d+)"', blk):
                if cid not in live:
                    stray.add(cid)
                    blk = re.sub(rf'<w:{tg}[^>]*w:id="{cid}"[^>]*/>', '', blk)
        merged[n] = blk
    if stray:
        print(f'  dangling anchors removed: {len(stray)} ({sorted(stray)})')

    # ---- verify -------------------------------------------------------------
    body = ''.join(merged)
    for cid in list(cdefs_b):
        ok = all(re.search(rf'<w:{tg}[^>]*w:id="{cid}"', body)
                 for tg in ('commentRangeStart', 'commentRangeEnd', 'commentReference'))
        if not ok:
            unanchored.append(cid)
            del cdefs_b[cid]
    if unanchored:
        print(f'  WARNING: {len(unanchored)} comment(s) could not be anchored '
              f'and were dropped: {sorted(set(unanchored))}', file=sys.stderr)

    new_doc = pre + ''.join(merged) + suf
    head = cm_b[:cm_b.index('>', cm_b.index('<w:comments')) + 1]
    new_comments = head + ''.join(cdefs_b[k] for k in sorted(cdefs_b, key=int)) + '</w:comments>'

    # Rebuild the package: every part copied byte-for-byte except the two we changed.
    # commentsExtended/Ids/Extensible are DROPPED for the ported ids rather than
    # faked — a stale paraId there makes Word rebuild threading wrongly.
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_p, 'w', zipfile.ZIP_DEFLATED) as zw:
        for item in zb.infolist():
            if item.filename == 'word/document.xml':
                zw.writestr(item, new_doc)
            elif item.filename == 'word/comments.xml':
                zw.writestr(item, new_comments)
            else:
                zw.writestr(item, zb.read(item.filename))

    rep = Path(a.report) if a.report else out_p.with_suffix(out_p.suffix + '.merge-report.md')
    L = [f'# Merge report — `{out_p.name}`', '',
         f'- base  : `{base_p.name}` ({len(cdefs_b) - len(ported)} comments)',
         f'- other : `{other_p.name}` ({len(cdefs_o)} comments)',
         f'- merged: **{len(cdefs_b)} comments**, {len(merged)} body blocks', '',
         f'Comments carried over: **{len(ported)}/{len(cdefs_o)}**. '
         f'Blocks taken from other: **{len(took_other)}**. '
         f'Blocks inserted: **{len(inserted)}**. '
         f'Prose conflicts: **{len(conflicts)}**.', '']
    if conflicts:
        L += ['## Prose conflicts — BOTH reviewers edited these; base won, resolve by hand', '']
        for idx, btxt, bs, os_ in conflicts:
            L += [f'### block {idx} — {btxt}', '', f'- **kept (base):** {bs}',
                  f'- **dropped (other):** {os_}', '']
    if took_other:
        L += ['## Blocks taken from --other (only that branch edited them)', '']
        L += [f'- block {i} — {t}' for i, t in took_other] + ['']
    if inserted:
        L += ['## Blocks that exist only in --other (inserted)', '']
        L += [f'- {k}: {t}' for k, t in inserted] + ['']
    if unanchored:
        L += ['## Comments that could not be anchored (DROPPED)', '']
        L += [f'- `{c}`' for c in sorted(set(unanchored))] + ['']
    if ported:
        L += ['## Comments carried over', '']
        L += [f'- `{i}` **{au}** — on "{an[:90]}"' for i, au, an in ported] + ['']
    rep.write_text('\n'.join(L), encoding='utf-8')

    print(f'merged -> {out_p}')
    print(f'  comments {len(cdefs_b) - len(ported)} + {len(ported)} = {len(cdefs_b)}')
    print(f'  blocks taken from other: {len(took_other)}; inserted: {len(inserted)}')
    print(f'  PROSE CONFLICTS NEEDING A HUMAN: {len(conflicts)}  (see {rep.name})')


if __name__ == '__main__':
    main()
