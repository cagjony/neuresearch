#!/usr/bin/env python3
"""
docx_form.py
============
Write into the cells of an official .docx form without disturbing it.

A grant form is a document whose own text - the instruction paragraph under
every heading, the footnote under every table - is part of what must be
submitted. Filling it therefore means adding paragraphs inside its cells, not
rebuilding the document. These helpers walk the body as items / rows / cells
and replace a cell's paragraphs while keeping its formatting, so the template
survives intact.

Used by fill_1001_form.py. Stdlib only.
"""

import html
import re
import zipfile

def body_items(xml):
    """Top-level (tag, start, end) for w:p / w:tbl inside w:body."""
    b = re.search(r'<w:body>', xml).end()
    e = xml.index('</w:body>')
    items, pos = [], b
    while pos < e:
        m = re.compile(r'<w:(p|tbl|sectPr)\b').search(xml, pos, e)
        if not m: break
        tag = m.group(1)
        sc = re.match(r'<w:p\b[^>]*/>', xml[m.start():])
        if tag == 'p' and sc:
            items.append((tag, m.start(), m.start()+len(sc.group(0)))); pos = m.start()+len(sc.group(0)); continue
        d, j = 0, m.start()
        pat = re.compile(rf'<w:{tag}\b[^>]*?(/?)>|</w:{tag}>')
        while True:
            n = pat.search(xml, j)
            if not n: break
            if n.group(0).startswith(f'</w:{tag}'): d -= 1
            elif n.group(1) != '/': d += 1
            j = n.end()
            if d == 0: break
        items.append((tag, m.start(), j)); pos = j
    return items

def spans(xml, tag, a, b):
    """Non-nested spans of <w:TAG> within [a,b)."""
    out, pos = [], a
    pat = re.compile(rf'<w:{tag}\b[^>]*?(/?)>|</w:{tag}>')
    while pos < b:
        m = re.compile(rf'<w:{tag}\b').search(xml, pos, b)
        if not m: break
        d, j = 0, m.start()
        while True:
            n = pat.search(xml, j, b)
            if not n: break
            if n.group(0).startswith(f'</w:{tag}'): d -= 1
            elif n.group(1) != '/': d += 1
            j = n.end()
            if d == 0: break
        out.append((m.start(), j)); pos = j
    return out

def text(s):
    t = ''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', s, re.S))
    return re.sub(r'<[^>]+>', '', t)

def esc(s):
    return html.escape(s, quote=False)

def runs_xml(runs, rpr):
    """Runs with explicit bold on/off - the cell's own rPr may already be bold."""
    out = ''
    for t, bold in runs:
        # the form's instruction paragraphs are italic; our answers are not
        r = rpr.replace('<w:i/>', '').replace('<w:iCs/>', '')
        if bold and '<w:b/>' not in r:
            m = re.search(r'<w:rFonts\b[^>]*/>', r)      # w:b must follow w:rFonts
            if m:
                r = r[:m.end()] + '<w:b/>' + r[m.end():]
            elif '<w:rPr>' in r:
                r = r.replace('<w:rPr>', '<w:rPr><w:b/>', 1)
            else:
                r = '<w:rPr><w:b/></w:rPr>'
        elif not bold:
            r = r.replace('<w:b/>', '').replace('<w:bCs/>', '')
        out += f'<w:r>{r}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>'
    return out


def fill_cell(xml, a, b, paras, bold_first=False, keep=0, force_body=False):
    """Replace the paragraphs of cell [a,b) with `paras`, keeping its pPr/rPr."""
    cell = xml[a:b]
    ps = list(re.finditer(r'<w:p\b.*?</w:p>|<w:p\b[^>]*/>', cell, re.S))
    # take formatting from the first paragraph we are about to replace, not from
    # a label/heading paragraph we are keeping (those are bold and centred)
    tpl = ps[keep].group(0) if len(ps) > keep else (ps[0].group(0) if ps else '<w:p/>')
    ppr = re.search(r'<w:pPr>.*?</w:pPr>', tpl, re.S)
    ppr = ppr.group(0) if ppr else ''
    rpr = re.search(r'<w:rPr>.*?</w:rPr>', tpl, re.S)
    rpr = rpr.group(0) if rpr else '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="18"/></w:rPr>'
    if force_body:   # the cell's own template paragraph is a bold, centred heading
        ppr = '<w:pPr><w:jc w:val="both"/></w:pPr>'
        rpr = ('<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
               '<w:color w:val="000000"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>')
    def mk(p, bold):
        runs = [(p, bold)] if isinstance(p, str) else p
        return f'<w:p>{ppr}{runs_xml(runs, rpr)}</w:p>'
    body = ''.join(mk(p, bold_first and i == 0) for i, p in enumerate(paras)) or '<w:p>%s</w:p>' % ppr
    s = ps[keep].start() if len(ps) > keep else len(cell)
    e = ps[-1].end() if ps else len(cell)
    return xml[:a] + cell[:s] + body + cell[e:] + xml[b:]

def load(p):
    return zipfile.ZipFile(p).read('word/document.xml').decode('utf-8')

def save(src, dst, xml):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in zin.infolist():
            zo.writestr(it, xml.encode('utf-8') if it.filename == 'word/document.xml' else zin.read(it.filename))


def paragraph_texts(xml):
    """Every paragraph's plain text, in document order - used to verify that the
    template's own instruction paragraphs and footnotes survived the filling."""
    return [text(m.group(0)).strip() for m in re.finditer(r'<w:p\b.*?</w:p>', xml, re.S)]
