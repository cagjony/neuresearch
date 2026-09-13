#!/usr/bin/env python3
r"""
fill_ek1.py
===========
Regenerate EK-1 (the reference list) from a project's manuscript.tex.

    python fill_ek1.py --vault /path/to/neubrain --project 1001-ob-pcx

EK-1 is a rendering of `\begin{thebibliography}`, so it is generated, never
hand-edited: a reference dropped from the manuscript must disappear from EK-1
and every later number must shift, and doing that by hand is how numbering and
citations drift apart. The numbering written here is the position in the list,
which is what \cite keys resolve to in the form.

Everything above the first entry - the heading and TÜBİTAK's instruction
paragraph - is left untouched.

Requires: Python 3.10+ (stdlib only), docx_form.py, tex_sections.py.
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

import docx_form as dx
from tex_sections import Manuscript, rich


def entries(m: Manuscript):
    """Every \\bibitem, in order, as rich runs."""
    body = m.tex[m.tex.index(r'\begin{thebibliography}'):m.tex.index(r'\end{thebibliography}')]
    out = []
    for i, (_, text) in enumerate(re.findall(r'\\bibitem\{(ref\d+)\}(.*?)(?=\\bibitem\{|$)',
                                             body, re.S), 1):
        runs = rich(text.strip())
        out.append([(f'[{i}] ', False)] + runs)
    return out


def main():
    ap = argparse.ArgumentParser(description='Regenerate EK-1 from manuscript.tex')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--project', required=True)
    ap.add_argument('--file', default='archive/docs/EK-1_KAYNAKLAR_v3.docx')
    a = ap.parse_args()

    proj = Path(a.vault) / 'projects' / a.project
    target = proj / a.file
    m = Manuscript(proj / 'manuscript.tex')
    refs = entries(m)

    xml = dx.load(target)
    ps = list(re.finditer(r'<w:p\b.*?</w:p>|<w:p\b[^>]*/>', xml, re.S))
    numbered = [p for p in ps if re.match(r'\[\d+\]', dx.text(p.group(0)).strip())]
    if not numbered:
        raise SystemExit(f'no numbered entries found in {target}')
    first, last = numbered[0], numbered[-1]
    print(f'  mevcut: {len(numbered)} kaynak -> yeni: {len(refs)}')

    tpl = first.group(0)
    ppr = re.search(r'<w:pPr>.*?</w:pPr>', tpl, re.S)
    ppr = ppr.group(0) if ppr else ''
    rpr = re.search(r'<w:rPr>.*?</w:rPr>', tpl, re.S)
    rpr = rpr.group(0) if rpr else ('<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>'
                                    '<w:sz w:val="18"/></w:rPr>')
    body = ''.join(f'<w:p>{ppr}{dx.runs_xml(r, rpr)}</w:p>' for r in refs)
    xml = xml[:first.start()] + body + xml[last.end():]

    tmp = str(target) + '.tmp'
    with zipfile.ZipFile(target) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in zin.infolist():
            zo.writestr(it, xml.encode('utf-8') if it.filename == 'word/document.xml'
                        else zin.read(it.filename))
    Path(tmp).replace(target)
    print('yazıldı:', target)


if __name__ == '__main__':
    main()
