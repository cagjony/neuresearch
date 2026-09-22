#!/usr/bin/env python3
r"""
apply_answers.py
================
Answer a reviewer's comments by EDITING the prose in colour, then removing the
comments that have actually been answered.

    python apply_answers.py --docx d7.docx --answers answers_ca01.md --out d7_ca01.docx

The edits are authored in `--answers`, which is the source of truth; the .docx is
generated from it and never hand-edited (the 1001 chain of custody, applied to a
document we do not own). New wording lands in colour so the applicant can see at a
glance what came from us — the reviewer's own text stays in its original colour.

Answers file — blocks separated by `## id=<comment id>`:

    ## id=3
    type: replace
    resolve: yes
    find: larger optical access
    text: more invasive surgical access to position the imaging optics

    ## id=274
    type: note
    text: Needs a real number before submission.

`replace`  swaps `find` for `text`, coloured. The phrase is located in the
           CONCATENATED text of the paragraph the comment is anchored in, so it is
           found even when Word has split it across runs or a tracked change sits
           in the middle. Surrounding runs keep their own formatting.
`table_fill`
           fills the table the comment is anchored in, from a grid written as one
           row per line with ' | ' between cells. A cell of '-' keeps what is
           already there; rows beyond the table's own are cloned from its last
           row, so a reviewer's 5-row skeleton takes a 7-row answer.
`table_new`
           inserts a bordered table after the commented paragraph — for a caption
           that was never given a table.
`para_after`
           inserts a coloured paragraph after the commented one, with no label —
           document text, not a remark. The way to ADD information in answer to a
           comment without rewriting what the applicant already wrote.
`heading_after`
           like `para_after`, but bold — a new section heading.
`revise`   keeps `find` visible but struck through, followed by `text` — a rewording
           the owner can compare against what was there.
`insert_after`
           inserts `text` right after `find`, leaving `find` itself untouched.
`strike_block`
           strikes every run of the addressed paragraph or table (a superseded table
           stays visible above its replacement, which `table_new` inserts).
`strike`   marks `find` as struck through, in the answer colour, instead of deleting
           it: text the owner wrote must stay visible until the owner removes it.
`note`     appends a LABELLED coloured paragraph — a remark to a reviewer rather
           than a text change. Cannot close a comment.
`resolve: yes`
           deletes that comment (definition and all three anchors) once its edit
           has been applied. Use it ONLY when the comment is genuinely closed: a
           comment still waiting on a fact must stay, or the applicant loses the
           record of what was asked. A resolve whose edit did not apply is refused.

Default colour blue (0000FF); `--color RRGGBB`, `--tag` for the note label.
The input is opened read-only. Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

T_RE = re.compile(r'<w:t(?:\s[^>]*)?>(.*?)</w:t>', re.S)
RUN_RE = re.compile(r'<w:r(?:\s[^>]*)?>.*?</w:r>', re.S)


def parse_answers(text: str) -> list[dict]:
    blocks, cur, key = [], None, None
    for raw in text.splitlines():
        m = re.match(r'^##\s*id\s*=\s*(\d+)\s*$', raw)
        if not m:
            m2 = re.match(r'^##\s*at\s*=\s*(.+?)\s*$', raw)
            if m2:
                if cur:
                    blocks.append(cur)
                # Address a paragraph by a unique snippet of its own text, for the
                # many paragraphs that carry no comment at all — compression has to
                # reach those too.
                cur = {'id': '', 'at': m2.group(1), 'type': 'note',
                       'find': '', 'text': '', 'resolve': '', 'widths': ''}
                key = None
                continue
        if m:
            if cur:
                blocks.append(cur)
            cur = {'id': m.group(1), 'at': '', 'type': 'note',
                   'find': '', 'text': '', 'resolve': '', 'widths': ''}
            key = None
            continue
        if cur is None:
            continue
        m = re.match(r'^(type|find|text|resolve|widths)\s*:\s*(.*)$', raw)
        if m:
            key = m.group(1)
            cur[key] = m.group(2)
        elif key in ('text', 'find'):
            cur[key] += ('\n' + raw) if cur[key] else raw
    if cur:
        blocks.append(cur)
    for b in blocks:
        b['text'] = b['text'].strip()
        b['find'] = b['find'].strip()
        b.setdefault('at', '')
        b.setdefault('widths', '')
    return [b for b in blocks if b['text'] or b['type'] in ('cut', 'resolve', 'strike', 'strike_block')]


def strike_all_runs(block: str, color: str) -> str:
    """Strike + colour every text run, keeping each run's own formatting otherwise."""
    mark = f'<w:strike/><w:color w:val="{color}"/>'
    def one(m):
        run = m.group(0)
        if not T_RE.search(run):
            return run
        run = re.sub(r'<w:color\b[^>]*/>', '', run)
        if '<w:rPr>' in run:
            return run.replace('</w:rPr>', mark + '</w:rPr>', 1)
        return re.sub(r'^(<w:r(?:\s[^>]*)?>)', r'\1<w:rPr>' + mark + '</w:rPr>', run, count=1)
    return RUN_RE.sub(one, block)


def insert_after_in_block(block: str, find: str, new: str, color: str) -> tuple[str, bool]:
    """Insert coloured `new` right after `find`; every existing run keeps its text."""
    runs = [(m.start(), m.end(), m.group(0)) for m in RUN_RE.finditer(block)
            if T_RE.search(m.group(0))]
    texts = [T_RE.search(r[2]).group(1) for r in runs]
    at = ''.join(texts).find(esc(find))
    if at < 0:
        return block, False
    end, cursor = at + len(esc(find)), 0
    for (s, e, run), txt in zip(runs, texts):
        if cursor < end <= cursor + len(txt):
            k = end - cursor
            piece = (set_run_text(run, txt[:k]) + coloured_runs(new, color)
                     + (set_run_text(run, txt[k:]) if txt[k:] else ''))
            return block[:s] + piece + block[e:], True
        cursor += len(txt)
    return block, False


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def coloured_runs(text: str, color: str, bold: bool = False, strike: bool = False) -> str:
    rpr = ('<w:rPr>' + ('<w:b/><w:bCs/>' if bold else '') + ('<w:strike/>' if strike else '')
           + f'<w:color w:val="{color}"/></w:rPr>')
    out = []
    for n, line in enumerate(text.split('\n')):
        if n:
            out.append(f'<w:r>{rpr}<w:br/></w:r>')
        out.append(f'<w:r>{rpr}<w:t xml:space="preserve">{esc(line)}</w:t></w:r>')
    return ''.join(out)


def set_run_text(run: str, new: str) -> str:
    """Same run, same formatting, different words. An empty result drops the run
    so we do not leave a <w:t/> that Word renders as a stray space."""
    if not new:
        return ''
    return T_RE.sub(lambda m: f'<w:t xml:space="preserve">{new}</w:t>', run, count=1)


def replace_in_block(block: str, find: str, new: str, color: str,
                     strike: bool = False) -> tuple[str, bool]:
    """Replace `find` across run boundaries inside one paragraph."""
    runs = [(m.start(), m.end(), m.group(0)) for m in RUN_RE.finditer(block)
            if T_RE.search(m.group(0))]
    if not runs:
        return block, False
    texts = [T_RE.search(r[2]).group(1) for r in runs]
    full = ''.join(texts)
    needle = esc(find)
    at = full.find(needle)
    if at < 0:                                   # tolerate differing whitespace
        flat = re.sub(r'\s+', ' ', full)
        n2 = re.sub(r'\s+', ' ', needle)
        if flat.find(n2) < 0:
            return block, False
        at, needle = full.find(n2.split(' ')[0]), n2
        if at < 0:
            return block, False
    end = at + len(needle)

    out, pos, cursor, inserted = [], 0, 0, False
    for (s, e, run), txt in zip(runs, texts):
        r_lo, r_hi = cursor, cursor + len(txt)
        cursor = r_hi
        out.append(block[pos:s]); pos = e
        if r_hi <= at or r_lo >= end:            # untouched run
            out.append(run); continue
        pre = txt[:max(0, at - r_lo)] if r_lo < at else ''
        post = txt[max(0, end - r_lo):] if r_hi > end else ''
        if pre:
            out.append(set_run_text(run, pre))
        if not inserted:
            out.append(coloured_runs(new, color, strike=strike))
            inserted = True
        if post:
            out.append(set_run_text(run, post))
    out.append(block[pos:])
    return ''.join(out), inserted



# ---------------------------------------------------------------- tables ----
# A reviewer's empty table skeleton and a caption with no table under it are both
# things that have to be FILLED, not commented on. Cell text is written in the
# answer colour like any other edit.

TR_RE = re.compile(r'<w:tr\b.*?</w:tr>', re.S)
TC_RE = re.compile(r'<w:tc(?:\s[^>]*)?>.*?</w:tc>', re.S)


def parse_grid(text: str) -> list[list[str]]:
    """Rows on their own line, cells separated by ' | '. A cell of '-' means
    leave whatever is already there."""
    grid = []
    for line in text.split('\n'):
        if not line.strip():
            continue
        grid.append([c.strip() for c in line.split('|')])
    return grid


def cell_content(text: str, color: str) -> str:
    return '<w:p>' + (coloured_runs(text, color) if text else '') + '</w:p>'


def visible(block: str) -> str:
    """Only <w:t>. A Zotero citation field carries a large JSON blob in
    <w:instrText>, which is field code, not text the reader ever sees — counting
    it makes a 129-word paragraph look like 909."""
    runs = re.findall(r'<w:t(?:\s[^>]*)?>(.*?)</w:t>', block, re.S)
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', '', ''.join(runs))).split())


def comment_ids(block: str) -> list[str]:
    return re.findall(r'<w:commentRangeStart[^>]*w:id="(\d+)"', block)


def balanced_end(s: str, tag: str, start: int) -> int:
    """Index just past the </tag> that closes the <tag ...> at `start`.

    Word nests a tracked-formatting change INSIDE the property element it
    describes: a <w:tcPr> contains a <w:tcPrChange> containing another
    <w:tcPr>, and <w:pPr> behaves the same way. A non-greedy regex closes on
    the INNER tag and silently yields unbalanced XML, which Word reports only
    as "the file is corrupt". Count depth instead.
    """
    pat = re.compile(rf'<(/?){tag}(?:\s[^>]*)?(/?)>')
    m = pat.match(s, start)
    if not m:
        return start
    if m.group(2):                          # self-closing
        return m.end()
    depth, pos = 1, m.end()
    while depth and (mm := pat.search(s, pos)):
        depth += -1 if mm.group(1) else (0 if mm.group(2) else 1)
        pos = mm.end()
    return pos


def set_cell(tc: str, text: str, color: str) -> str:
    """Replace a cell body, keeping its <w:tcPr> (width, borders, shading)."""
    m = re.match(r'<w:tc(?:\s[^>]*)?>', tc)
    at = m.end() if m else len('<w:tc>')
    if re.compile(r'\s*<w:tcPr(?:\s[^>]*)?[>/]').match(tc, at):
        at = balanced_end(tc, 'w:tcPr', tc.index('<w:tcPr', at))
    return tc[:at] + cell_content(text, color) + '</w:tc>'

def fill_table(tbl: str, grid: list[list[str]], color: str) -> str:
    rows = TR_RE.findall(tbl)
    if not rows:
        return tbl
    ncol = len(TC_RE.findall(rows[0]))
    out_rows = []
    for i, want in enumerate(grid):
        if want and want[0].strip().upper() == 'DELETE':
            continue                                # drop this row entirely
        if i < len(rows):
            row = rows[i]
            cells = TC_RE.findall(row)
            new_cells, pos, parts = [], 0, []
            for j, tc in enumerate(cells):
                at = row.index(tc, pos)
                parts.append(row[pos:at])
                val = want[j] if j < len(want) else ''
                parts.append(tc if val == '-' else set_cell(tc, val, color))
                pos = at + len(tc)
            parts.append(row[pos:])
            out_rows.append(''.join(parts))
        else:                                  # more data than rows: clone the last
            proto = rows[-1]
            cells = TC_RE.findall(proto)
            pos, parts = 0, []
            for j, tc in enumerate(cells):
                at = proto.index(tc, pos)
                parts.append(proto[pos:at])
                val = want[j] if j < len(want) else ''
                parts.append(set_cell(tc, '' if val == '-' else val, color))
                pos = at + len(tc)
            parts.append(proto[pos:])
            out_rows.append(''.join(parts))
    # keep any table rows the grid did not reach
    out_rows.extend(rows[len(grid):])
    head = tbl[:tbl.index(rows[0])]
    return head + ''.join(out_rows) + '</w:tbl>'


def new_table(grid: list[list[str]], color: str, weights: list[int] | None = None) -> str:
    """A plain bordered table across the usual 9072-twip text column. `weights`
    shares the width out unevenly — a risk table needs a wide measures column and
    narrow probability/impact ones, and equal columns make it three times taller
    than it needs to be."""
    ncol = max(len(r) for r in grid)
    if weights and len(weights) == ncol and sum(weights) > 0:
        tot = sum(weights)
        cols = [max(400, 9072 * x // tot) for x in weights]
    else:
        cols = [9072 // ncol] * ncol
    w = cols[0]
    borders = ''.join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
                      for e in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    gridcols = ''.join('<w:gridCol w:w="%d"/>' % c for c in cols)
    out = ['<w:tbl><w:tblPr><w:tblW w:w="9072" w:type="dxa"/>'
           '<w:tblBorders>' + borders + '</w:tblBorders></w:tblPr>'
           '<w:tblGrid>' + gridcols + '</w:tblGrid>']
    for r in grid:
        out.append('<w:tr>')
        for j in range(ncol):
            val = r[j] if j < len(r) else ''
            out.append(f'<w:tc><w:tcPr><w:tcW w:w="{cols[j]}" w:type="dxa"/></w:tcPr>'
                       + cell_content(val, color) + '</w:tc>')
        out.append('</w:tr>')
    out.append('</w:tbl>')
    return ''.join(out)


def strip_comment(doc: str, cid: str) -> str:
    for tag in ('commentRangeStart', 'commentRangeEnd'):
        doc = re.sub(rf'<w:{tag}[^>]*w:id="{cid}"[^>]*/>', '', doc)
    # the reference lives in its own run; take the run with it
    doc = re.sub(rf'<w:r(?:\s[^>]*)?>(?:(?!</w:r>).)*?<w:commentReference[^>]*w:id="{cid}"[^>]*/>'
                 rf'(?:(?!</w:r>).)*?</w:r>', '', doc, flags=re.S)
    doc = re.sub(rf'<w:commentReference[^>]*w:id="{cid}"[^>]*/>', '', doc)
    return doc


def split_blocks(doc: str) -> tuple[str, list[str], str]:
    m = re.search(r'<w:body[^>]*>', doc)
    start, end = m.end(), doc.rindex('</w:body>')
    inner, blocks, pos = doc[start:end], [], 0
    while pos < len(inner):
        nxt = None
        for tag in ('w:p', 'w:tbl', 'w:sdt'):
            hit = re.compile(rf'<{tag}(?:\s[^>]*)?(/?)>').search(inner, pos)
            if hit and (nxt is None or hit.start() < nxt[0].start()):
                nxt = (hit, tag)
        if nxt is None:
            break
        hit, tag = nxt
        if hit.group(1) == '/':
            blocks.append(inner[hit.start():hit.end()]); pos = hit.end(); continue
        depth, scan = 1, hit.end()
        pat = re.compile(rf'<(/?){tag}(?:\s[^>]*)?(/?)>')
        while depth and (mm := pat.search(inner, scan)):
            depth += -1 if mm.group(1) else (0 if mm.group(2) else 1)
            scan = mm.end()
        blocks.append(inner[hit.start():scan]); pos = scan
    return doc[:start], blocks, doc[end:]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--docx', required=True)
    ap.add_argument('--answers', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--color', default='0000FF')
    ap.add_argument('--tag', default='CA01')
    a = ap.parse_args()

    src, out_p = Path(a.docx), Path(a.out)
    if out_p.resolve() == src.resolve():
        sys.exit('apply_answers: --out would overwrite --docx. Refusing.')
    if not re.fullmatch(r'[0-9A-Fa-f]{6}', a.color):
        sys.exit('apply_answers: --color must be six hex digits, e.g. 0000FF')

    z = zipfile.ZipFile(src)
    doc = z.read('word/document.xml').decode('utf-8')
    cxml = z.read('word/comments.xml').decode('utf-8') if 'word/comments.xml' in z.namelist() else ''
    author = {m.group(1): m.group(2) for m in
              re.finditer(r'<w:comment\b[^>]*w:id="(\d+)"[^>]*w:author="([^"]*)"', cxml)}

    pre, blocks, suf = split_blocks(doc)
    edited, noted, resolved, failed, cut_words = [], [], [], [], []

    for b in parse_answers(Path(a.answers).read_text(encoding='utf-8')):
        cid = b['id']
        if b['at']:
            snippet = b['at']
            hits = [n for n, blk in enumerate(blocks) if snippet in visible(blk)]
            if len(hits) != 1:
                failed.append((b['at'][:40],
                               f'snippet matches {len(hits)} paragraphs, need exactly 1'))
                continue
            idx, cid = hits[0], ''
        else:
            idx = next((n for n, blk in enumerate(blocks)
                        if re.search(rf'<w:commentRangeStart[^>]*w:id="{cid}"', blk)), None)
            if idx is None:
                failed.append((cid, 'no paragraph carries this comment id')); continue
        who = (author.get(cid) or '?').split()[0]

        if b['type'] == 'resolve':
            # Close a comment the document already answers as it stands — a
            # page-limit reminder once the limit is met, say. Nothing is
            # written: the justification belongs in the answers file, which is
            # what the run is reproducible from.
            if not cid:
                failed.append((b['at'][:40],
                               'resolve: address the comment by id, not by snippet'))
                continue
            resolved.append(cid)
            continue
        if b['type'] == 'cut':
            # Remove a paragraph outright. Any comment anchored in it goes too —
            # the text it pointed at no longer exists — and each is named in the
            # run report so nothing disappears silently.
            gone = comment_ids(blocks[idx])
            resolved.extend(g for g in gone if g not in resolved)
            cut_words.append((b['at'][:60] or cid, len(visible(blocks[idx]).split()), gone))
            del blocks[idx]
            continue
        if b['type'] in ('para_after', 'heading_after'):
            # A new paragraph in the answer colour, carrying NO tag — this is
            # document text the applicant may keep, not a remark addressed to a
            # reviewer. Use it to ADD information without touching what is there.
            # It takes the anchor's paragraph spacing so only the colour differs
            # (minus list numbering and paragraph-mark formatting, which belong to
            # the anchor alone).
            m = re.search(r'<w:pPr>.*?</w:pPr>', blocks[idx], re.S)
            ppr = re.sub(r'<w:rPr>.*?</w:rPr>|<w:numPr>.*?</w:numPr>', '', m.group(0), flags=re.S) if m else ''
            blocks.insert(idx + 1, '<w:p>' + ppr
                          + coloured_runs(b['text'], a.color, bold=b['type'] == 'heading_after') + '</w:p>')
            edited.append((cid, who))
        elif b['type'] in ('revise', 'insert_after'):
            if b['type'] == 'revise':
                new_blk, ok = replace_in_block(blocks[idx], b['find'], b['find'], a.color, strike=True)
                if ok:
                    new_blk, ok = insert_after_in_block(new_blk, b['find'], ' ' + b['text'], a.color)
            else:
                new_blk, ok = insert_after_in_block(blocks[idx], b['find'], b['text'], a.color)
            if not ok:
                failed.append((cid or b['at'][:40], f'phrase not found in its paragraph: {b["find"][:60]!r}'))
                continue
            blocks[idx] = new_blk
            edited.append((cid, who))
        elif b['type'] == 'strike_block':
            blocks[idx] = strike_all_runs(blocks[idx], a.color)
            edited.append((cid, who))
        elif b['type'] == 'strike':
            new_blk, ok = replace_in_block(blocks[idx], b['find'], b['find'], a.color, strike=True)
            if not ok:
                failed.append((cid or b['at'][:40], f'phrase not found in its paragraph: {b["find"][:60]!r}'))
                continue
            blocks[idx] = new_blk
            edited.append((cid, who))
        elif b['type'] == 'table_fill':
            if not blocks[idx].startswith('<w:tbl'):
                failed.append((cid, 'table_fill: this comment is not anchored in a table'))
                continue
            blocks[idx] = fill_table(blocks[idx], parse_grid(b['text']), a.color)
            edited.append((cid, who))
        elif b['type'] == 'table_new':
            ws = [int(x) for x in b['widths'].split()] if b['widths'].strip() else None
            blocks.insert(idx + 1, new_table(parse_grid(b['text']), a.color, ws))
            edited.append((cid, who))
        elif b['type'] == 'replace':
            new_blk, ok = replace_in_block(blocks[idx], b['find'], b['text'], a.color)
            if not ok:
                failed.append((cid, f'phrase not found in its paragraph: {b["find"][:60]!r}'))
                continue
            blocks[idx] = new_blk
            edited.append((cid, who))
        else:
            note = f'[{a.tag} → {who} #{cid}] ' + b['text']
            blocks[idx] += '<w:p>' + coloured_runs(note, a.color) + '</w:p>'
            noted.append((cid, who))

        if b['resolve'].strip().lower() in ('yes', 'true', '1'):
            if b['type'] not in ('replace', 'table_fill', 'table_new', 'para_after', 'heading_after', 'strike', 'revise', 'insert_after', 'strike_block'):
                failed.append((cid, 'resolve: yes on a note — a remark does not close a comment'))
                continue
            resolved.append(cid)

    body = ''.join(blocks)
    for cid in resolved:
        body = strip_comment(body, cid)
    if resolved:
        keep = []
        for m in re.finditer(r'<w:comment\b[^>]*>.*?</w:comment>', cxml, re.S):
            cid = re.search(r'w:id="(\d+)"', m.group(0)).group(1)
            if cid not in resolved:
                keep.append(m.group(0))
        head = cxml[:cxml.index('>', cxml.index('<w:comments')) + 1]
        cxml = head + ''.join(keep) + '</w:comments>'

    new_doc = pre + body + suf
    try:
        ET.fromstring(new_doc.encode('utf-8'))
        if cxml:
            ET.fromstring(cxml.encode('utf-8'))
    except ET.ParseError as e:
        sys.exit(f'apply_answers: generated XML is not well-formed ({e}). Nothing written.')

    out_p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_p, 'w', zipfile.ZIP_DEFLATED) as zw:
        for item in z.infolist():
            if item.filename == 'word/document.xml':
                zw.writestr(item, new_doc)
            elif item.filename == 'word/comments.xml' and cxml:
                zw.writestr(item, cxml)
            else:
                zw.writestr(item, z.read(item.filename))

    print(f'wrote {out_p}')
    print(f'  text edits in colour : {len(edited)}')
    print(f'  notes added          : {len(noted)}')
    print(f'  comments resolved    : {len(resolved)}')
    if cut_words:
        print(f'  paragraphs cut       : {len(cut_words)}'
              f'  ({sum(w for _, w, _ in cut_words)} visible words)')
        for who, w, gone in cut_words:
            print(f'    - {w:4}w  {who}' + (f'   (comments removed: {gone})' if gone else ''))
    if failed:
        print(f'  NOT APPLIED ({len(failed)}):')
        for cid, why in failed:
            print(f'    id={cid}: {why}')


if __name__ == '__main__':
    main()
