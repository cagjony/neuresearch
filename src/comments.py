#!/usr/bin/env python3
r"""
comments.py
===========
Read the feedback a co-author left on a .docx.

    python comments.py <file.docx>                 comments + tracked changes
    python comments.py <file.docx> --diff <ref>    plain edits, against <ref>

Word and LibreOffice write the same three places, and a reviewer may use any of
them, so all three are read:

  comments          -> word/comments.xml, printed next to the text they mark
  tracked changes   -> w:ins / w:del in the body, with their author
  untracked edits   -> no trace at all; found by diffing against the generated
                       file, paragraph by paragraph

Report-only: never modifies the file it reads. Stdlib only.
"""

import sys, re, zipfile, html, difflib

def text(s):
    t = ''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', s, re.S))
    return html.unescape(re.sub(r'<[^>]+>', '', t))

def load(p, part='word/document.xml'):
    z = zipfile.ZipFile(p)
    return z.read(part).decode('utf-8') if part in z.namelist() else None

def paragraphs(doc):
    return [text(m.group(0)).strip() for m in re.finditer(r'<w:p\b.*?</w:p>', doc, re.S)]

def comments(path):
    cm = load(path, 'word/comments.xml')
    if not cm:
        print('Yorum: yok\n'); return
    doc = load(path)
    out = []
    for c in re.finditer(r'<w:comment\b([^>]*)>(.*?)</w:comment>', cm, re.S):
        at = dict(re.findall(r'w:(\w+)="([^"]*)"', c.group(1)))
        cid = at.get('id')
        a = re.search(rf'<w:commentRangeStart[^>]*w:id="{cid}"[^>]*/>', doc)
        b = re.search(rf'<w:commentRangeEnd[^>]*w:id="{cid}"[^>]*/>', doc)
        span = text(doc[a.end():b.start()]) if a and b else '(çapa bulunamadı)'
        out.append((cid, at.get('author', '?'), at.get('date', '')[:16],
                    text(c.group(2)).strip(), span.strip()))
    print(f'Yorum: {len(out)}\n')
    for cid, au, dt, body, span in out:
        print(f'--- #{cid}  {au}  {dt}')
        print(f'    metin : {span[:300]}')
        print(f'    yorum : {body}\n')

def revisions(path):
    doc = load(path)
    ins = [(dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(1))), text(m.group(2)))
           for m in re.finditer(r'<w:ins\b([^>]*)>(.*?)</w:ins>', doc, re.S)]
    dele = [(dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(1))),
             html.unescape(re.sub(r'<[^>]+>', '', ''.join(
                 re.findall(r'<w:delText[^>]*>(.*?)</w:delText>', m.group(2), re.S)))))
            for m in re.finditer(r'<w:del\b([^>]*)>(.*?)</w:del>', doc, re.S)]
    ins = [(a, t) for a, t in ins if t.strip()]
    dele = [(a, t) for a, t in dele if t.strip()]
    print(f'Değişiklik izi: {len(ins)} ekleme, {len(dele)} silme\n')
    for a, t in ins:
        print(f'  + [{a.get("author","?")}] {t[:220]}')
    for a, t in dele:
        print(f'  - [{a.get("author","?")}] {t[:220]}')
    if ins or dele:
        print()

def diff(path, ref):
    a, b = paragraphs(load(ref)), paragraphs(load(path))
    a = [p for p in a if p]; b = [p for p in b if p]
    n = 0
    for line in difflib.unified_diff(a, b, 'üretilen', 'gelen', n=0, lineterm=''):
        if line.startswith(('---', '+++', '@@')):
            continue
        n += 1
        print(('  DEĞİŞTİ ' if line[0] == '+' else '  ÖNCE   ') + line[1:][:240])
    print(f'\nDüz düzenleme: {n} paragraf farkı')

if __name__ == '__main__':
    p = sys.argv[1]
    if '--diff' in sys.argv:
        diff(p, sys.argv[sys.argv.index('--diff') + 1])
    else:
        comments(p); revisions(p)
