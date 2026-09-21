#!/usr/bin/env python3
"""
page_budget.py — count an ERC PoC Part B the way the evaluator counts it.

    python page_budget.py part_b.docx

The ERC PoC 2026 Information for Applicants (v1.9) sets an overall limit of
10 pages, "excluding the cover page with headers and abstract, references and
the risk mitigation table", and says it "will be strictly applied": reviewers
"will be under no obligation to read beyond" it. So a raw page count is the
wrong number twice over — it counts excluded matter, and it counts tracked
changes and comment anchors the evaluator never sees.

This renders the document as the evaluator gets it (all tracked changes
accepted, comments hidden), then reports pages per section against the limits.
Needs libreoffice + pdfinfo/pdftotext on PATH.
"""
import re, subprocess, sys, tempfile, xml.etree.ElementTree as ET, zipfile
from pathlib import Path

LIMITS = {'1a': 3, '1b': 6, '1c': 1}
TOTAL = 10


def accept_changes(src: Path, dst: Path) -> None:
    z = zipfile.ZipFile(src)
    d = z.read('word/document.xml').decode('utf-8')
    # self-closing marks first: <w:del/> inside a run or paragraph property is
    # not a container, and treating it as one makes the paired pattern swallow
    # real text.
    d = re.sub(r'<w:(?:del|ins)\b[^>]*/>', '', d)
    d = re.sub(r'<w:del\b[^>]*>.*?</w:del>', '', d, flags=re.S)
    d = re.sub(r'</?w:ins\b[^>]*>', '', d)
    for tg in ('pPrChange', 'rPrChange', 'tcPrChange', 'tblPrChange',
               'trPrChange', 'sectPrChange'):
        d = re.sub(rf'<w:{tg}\b.*?</w:{tg}>', '', d, flags=re.S)
    for tg in ('commentRangeStart', 'commentRangeEnd'):
        d = re.sub(rf'<w:{tg}[^>]*/>', '', d)
    d = re.sub(r'<w:r(?:\s[^>]*)?>(?:(?!</w:r>).)*?<w:commentReference[^>]*/>'
               r'(?:(?!</w:r>).)*?</w:r>', '', d, flags=re.S)
    ET.fromstring(d.encode('utf-8'))
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zw:
        for it in z.infolist():
            zw.writestr(it, d if it.filename == 'word/document.xml'
                        else z.read(it.filename))


def main() -> None:
    src = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        clean = td / 'clean.docx'
        accept_changes(src, clean)
        subprocess.run(['soffice', '--headless', '--norestore',
                        f'-env:UserInstallation=file://{td}/lo',
                        '--convert-to', 'pdf', '--outdir', str(td), str(clean)],
                       capture_output=True, timeout=600)
        pdf = td / 'clean.pdf'
        if not pdf.exists():
            sys.exit('page_budget: LibreOffice produced no PDF')
        n = int(re.search(r'Pages:\s+(\d+)', subprocess.run(
            ['pdfinfo', str(pdf)], capture_output=True, text=True).stdout).group(1))
        pg = {p: subprocess.run(['pdftotext', '-layout', '-f', str(p), '-l', str(p),
                                 str(pdf), '-'], capture_output=True, text=True).stdout
              for p in range(1, n + 1)}

    def find(pat, frm=1):
        return next((p for p in range(frm, n + 1)
                     if re.search(pat, pg[p], re.M | re.I)), None)

    a, b, c = find(r'^\s*Section 1a'), find(r'^\s*Section 1b'), find(r'^\s*Section 1c')
    # The excluded matter starts where the risk-mitigation TABLE starts, not at
    # the prose paragraph in 1c that introduces it — anchoring on that sentence
    # put the boundary one page early and under-reported the total by a page.
    risk = find(r'^\s*Table\s*\d*\.?\s*Risk mitigation|Risk\s+Description', c or 1)
    refs = find(r'^\s*(References|Bibliography)\s*$', risk or c or 1)
    # Sections are counted inclusively: a section whose last page also carries
    # the start of excluded matter still occupies that page.
    spans = {'1a': (b - a) if a and b else None,
             '1b': (c - b) if b and c else None,
             '1c': ((risk or refs or n + 1) - c) if c else None}
    print(f'{src.name}: {n} rendered pages (changes accepted, comments hidden)')
    counted = 0
    for k in ('1a', '1b', '1c'):
        s = spans[k]
        if s is None:
            print(f'  Section {k}: not found'); continue
        counted += s
        flag = 'ok' if s <= LIMITS[k] else f'OVER by {s - LIMITS[k]}'
        print(f'  Section {k}: {s} pages (max {LIMITS[k]})  {flag}')
    if risk and refs:
        print(f'  risk mitigation table: {refs - risk} pages   EXCLUDED')
    if refs:
        print(f'  references           : {n - refs + 1} pages   EXCLUDED')
    # A section whose last page also carries the start of the excluded table
    # still occupies that page. spans measures heading-to-heading, so that page
    # is missing from the sum unless the table starts at the top of it.
    if risk:
        head = next((l for l in pg[risk].splitlines() if l.strip()), '')
        if not re.match(r'\s*Table\s*\d*\.?\s*Risk mitigation', head, re.I):
            counted += 1
            print('  + 1 page shared with the start of the risk table')
    print(f'  COUNTED TOTAL: {counted} / {TOTAL}'
          f'{"" if counted <= TOTAL else f"   -> must lose {counted - TOTAL} pages"}')


if __name__ == '__main__':
    main()
