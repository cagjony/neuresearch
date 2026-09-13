#!/usr/bin/env python3
r"""
fill_1001_form.py
=================
Fill TÜBİTAK's official 1001 application form from a project's manuscript.tex.

    python fill_1001_form.py --vault /path/to/neubrain --project 1001-ob-pcx

Reads the pristine blank form saved from TÜBİTAK's .doc, writes every section
into its own cell, and leaves the form's own text alone: the instruction
paragraph under each heading, the footnote under each table, the full field
labels. The call forbids altering the format, so nothing of the template is
removed - content is added beneath what is already there.

    <project>/manuscript.tex                              content
    <project>/archive/docs/bos_basvuru_formlari/…docx     blank template
    <project>/figures/*.png                               figures
    -> <project>/archive/docs/1001_BASVURU_FORMU_v3.docx

Rebuild after every edit to manuscript.tex; the form is a rendering, never the
place to fix text. Regenerating also guarantees the submitted file carries no
comments or tracked changes.

Requires: Python 3.10+ (stdlib only), docx_form.py and tex_sections.py.
"""

from __future__ import annotations

import argparse
import html
import re
import zipfile
from pathlib import Path

import docx_form as dx
from tex_sections import Manuscript, flat, rich

CM = 360000                     # EMU per centimetre
FIG_CM = {                      # published width, height per figure
    'olfactory_chain.png': (7.0, 11.8),
    'drn_workflow.png': (16.0, 5.42),
    'relay_gonogo.png': (16.0, 3.33),
}
FIG_PLACE = [                   # (file, body item, insert after paragraph, Şekil n)
    ('olfactory_chain.png', 21, 1, 1),
    ('drn_workflow.png', 21, 7, 2),
    ('relay_gonogo.png', 35, None, 3),
]
BODY_CELLS = {'ÖZET', 'Summary'}        # these open with a bold, centred heading


# ---------------------------------------------------------------- the manuscript

def gantt(m: Manuscript):
    """(no, name, weight, who, months) per work package, from the İş-Zaman tables."""
    legend = dict(re.findall(r'(\w+) = ([^;.]+)',
                             m.tex[m.tex.index('PY = '):m.tex.index('PY = ') + 400]))
    rows: dict[str, dict] = {}
    for tbl in re.findall(r'\\begin\{tabular\}\{@\{\}l R\{4\.2cm\} c l \*\{12\}\{M\}@\{\}\}(.*?)\\end\{tabular\}',
                          m.tex, re.S):
        head = re.search(r'\\textbf\{Kim\}(.*?)\\\\', tbl, re.S).group(1)
        first = int(re.search(r'&\s*(\d+)', head).group(1))
        for line in re.findall(r'^İP(\d) & (.*?)\\\\$', tbl, re.M | re.S):
            no, rest = line
            c = [x.strip() for x in re.split(r'(?<!\\)&', rest)]
            r = rows.setdefault(no, {'name': tex_plain(c[0]), 'weight': c[1],
                                     'who': c[2], 'months': set()})
            for k, cell in enumerate(c[3:15]):
                if 'bullet' in cell:
                    r['months'].add(first + k)
    out = []
    for no in sorted(rows):
        r = rows[no]
        who = ', '.join(legend.get(k.strip(), k.strip()) for k in r['who'].split(','))
        out.append((no, r['name'], r['weight'], who, r['months']))
    return out


def tex_plain(s):
    from tex_sections import tex2txt
    return tex2txt(s)


# ------------------------------------------------------------------- the filling

def stage_text(m, xml, items):
    """Title block, ÖZET, the English abstract, §1.1-1.3 and §2."""
    title_tr = tex_plain(re.search(r'\{\\large (Koku yolağında.*?)\}\\\\', m.tex, re.S).group(1))
    pi = re.search(r'\\textbf\{Proje Yürütücüsü:\} & ([^\\]+)', m.tex).group(1).strip()
    org = re.search(r'\\textbf\{Projenin Yürütüleceği Kurum/Kuruluş:\} & ([^\\]+)', m.tex).group(1).strip()

    ozet = m.paras(r'\addcontentsline{toc}{section}{ÖZET}', r'\vspace{0.8em}\hrule\vspace{0.8em}')
    kw_tr = flat(ozet.pop())
    en = m.paras(r'\subsection*{Abstract (EN)}', r'\newpage')
    title_en = flat(en.pop(0)).replace('Title : ', '')
    kw_en = flat(en.pop())

    def cell(i, row=0, col=0):
        _, a, b = items[i]
        ra, rb = dx.spans(xml, 'tr', a, b)[row]
        return dx.spans(xml, 'tc', ra, rb)[col]

    return [
        (cell(6, 0), [[('Proje Başlığı: ', True), (title_tr, False)]], 0, 'Proje Başlığı'),
        (cell(6, 1), [[('Proje Yürütücüsü: ', True), (pi, False)]], 0, 'Proje Yürütücüsü'),
        (cell(6, 2), [[('Projenin Yürütüleceği Kurum/Kuruluş: ', True), (org, False)]], 0, 'Kurum'),
        (cell(12, 0), ozet, 1, 'ÖZET'),
        (cell(12, 1), [[('Anahtar Kelimeler: ', True), (kw_tr.split(': ', 1)[1], False)]], 0, 'Anahtar Kelimeler'),
        (cell(15, 0), [[('Title : ', True), (title_en, False)]], 0, 'Title'),
        (cell(15, 1), en, 1, 'Summary'),
        (cell(15, 2), [[('Keywords: ', True), (kw_en.split(': ', 1)[1], False)]], 0, 'Keywords'),
        (cell(21, 0), m.paras(r'\subsection{Konunun Önemi ve Projenin Özgün Değeri}',
                              r'\subsection{Araştırma Sorusu ve/veya Hipotezi}'), 0, '§1.1'),
        (cell(25, 0), m.paras(r'\subsection{Araştırma Sorusu ve/veya Hipotezi}',
                              r'\subsection{Amaç ve Hedefler}'), 0, '§1.2'),
        (cell(29, 0), m.paras(r'\subsection{Amaç ve Hedefler}', r'\section{YÖNTEM}'), 0, '§1.3'),
        (cell(35, 0), m.paras(r'\section{YÖNTEM}', r'\section{PROJE YÖNETİMİ}'), 0, '§2 YÖNTEM'),
    ]


def stage_packages(m, xml):
    """The three İş Paketi tables, each with its risks inside it, and the Gantt."""
    pkgs = {p['İP No:'].strip(): p for p in m.packages()}
    risks = m.risks()
    items = dx.body_items(xml)
    _, ta, tb = items[59]
    tpl = xml[ta:tb]
    rows = dx.spans(tpl, 'tr', 0, len(tpl))
    risk_tpl = tpl[rows[8][0]:rows[8][1]]

    def build(no):
        p = pkgs[no]
        t = tpl
        rws = dx.spans(t, 'tr', 0, len(t))
        mine = [(d, mit) for ip, d, mit in risks if ip == 'İP' + no]
        t = t[:rws[9][1]] + risk_tpl * max(0, len(mine) - 2) + t[rws[9][1]:]
        rws = dx.spans(t, 'tr', 0, len(t))

        def c(r, i=0):
            return dx.spans(t, 'tc', *rws[r])[i]

        jobs = []
        for k, (rd, rm) in enumerate(mine):
            cs = dx.spans(t, 'tc', *rws[8 + k])
            jobs += [(cs[0], [rich(rd)], 0), (cs[1], [rich(rm)], 0)]
        people = [rich(x) for x in p["İP'yi Gerçekleştirecek Kişi(ler) ve İP'ye Katkıları:"].split(r'\newline')]
        jobs += [
            (c(1, 0), [[('İP No: ', True), (no, False)]], 0),
            (c(1, 1), [[('İP Adı: ', True), (tex_plain(p['İP Adı:']), False)]], 0),
            (c(2, 0), [[('İP Hedefi: ', True)] + rich(p['İP Hedefi:'])], 0),
            (c(3, 0), [[('İP Kapsamında Yapılacak İşler/Görevler: ', True)]
                       + rich(p['İP Kapsamında Yapılacak İşler/Görevler:'])], 0),
            (c(3, 1), people, 1),
            (c(4, 0), [rich(p['Başarı Ölçütü:'])], 1),     # keep the form's instruction
            (c(5, 0), [rich(p['Ara Çıktılar:'])], 1),
        ]
        for (a, b), pr, keep in sorted(jobs, key=lambda j: -j[0][0]):
            t = dx.fill_cell(t, a, b, pr, keep=keep)
        return t

    tables = [build(n) for n in ('1', '2', '3')]
    xml = xml[:ta] + '<w:p/>'.join(tables) + xml[tb:]

    plan = gantt(m)
    items = dx.body_items(xml)
    _, ga, gb = items[50]
    g = xml[ga:gb]
    grows = dx.spans(g, 'tr', 0, len(g))
    g = g[:grows[2 + len(plan)][0]] + g[grows[-1][1]:]      # drop the unused İP rows
    grows = dx.spans(g, 'tr', 0, len(g))
    for k, (no, name, weight, who, months) in reversed(list(enumerate(plan))):
        cs = dx.spans(g, 'tc', *grows[2 + k])
        vals = ['İP' + no, name, weight, who] + ['X' if mo in months else '' for mo in range(1, 37)]
        for (a, b), v in sorted(zip(cs, vals), key=lambda z: -z[0][0]):
            g = dx.fill_cell(g, a, b, [[(v, False)]] if v else [])
    return xml[:ga] + g + xml[gb:], len(tables), plan


def stage_impact(m, xml):
    """§3.2 Araştırma Olanakları, §4.1-4.3 and the closing free section."""
    def item(i):
        return dx.body_items(xml)[i]

    olanak = m.rows(r'\textbf{Projede Kullanım Amacı}\\', r'\end{tabularx}', 3)
    _, a, b = item(76)
    tbl = xml[a:b]
    rws = dx.spans(tbl, 'tr', 0, len(tbl))
    tbl = tbl[:rws[1][1]] + tbl[rws[1][0]:rws[1][1]] * (len(olanak) - 1) + tbl[rws[1][1]:]
    rws = dx.spans(tbl, 'tr', 0, len(tbl))
    jobs = []
    for k, r in enumerate(olanak):
        cs = dx.spans(tbl, 'tc', *rws[1 + k])
        jobs += [(cs[i], [r[i]]) for i in range(3)]
    for (ca, cb), pr in sorted(jobs, key=lambda j: -j[0][0]):
        tbl = dx.fill_cell(tbl, ca, cb, pr)
    xml = xml[:a] + tbl + xml[b:]

    cikti = m.rows(r'\textbf{Öngörülen Zaman Aralığı}\\', r'\end{tabularx}', 3)
    _, a, b = item(88)
    tbl = xml[a:b]
    rws = dx.spans(tbl, 'tr', 0, len(tbl))
    jobs = []
    for k, r in enumerate(cikti):
        cs = dx.spans(tbl, 'tc', *rws[1 + k])
        jobs += [(cs[1], [r[1]]), (cs[2], [r[2]])]     # column 0 already names the type
    for (ca, cb), pr in sorted(jobs, key=lambda j: -j[0][0]):
        tbl = dx.fill_cell(tbl, ca, cb, pr)
    xml = xml[:a] + tbl + xml[b:]

    etki = m.rows(r'\textbf{Etkinin Oluşması Öngörülen Zaman}\\', r'\end{longtable}', 3)
    paras = [[(flat(r[0]) + '. ', True)] + r[1] + [(' Öngörülen zaman: ' + flat(r[2]) + '.', False)]
             for r in etki]
    paras += m.paras(r'\noindent\textbf{ÖNGÖRÜLEN UYGULAMA ALANLARI.}',
                     r'\subsection{Proje Sonuçlarının Yayılımı')
    paras[len(etki)] = [('ÖNGÖRÜLEN UYGULAMA ALANLARI. ', True)] + paras[len(etki)]
    _, a, b = item(100)
    ca, cb = dx.spans(xml, 'tc', a, b)[0]
    xml = dx.fill_cell(xml, ca, cb, paras)

    yay = m.rows(r'\textbf{Etkinliğin Zamanı ve Süresi}\\', r'\end{longtable}', 3)
    fields = m.description(r'\subsection{Proje Sonuçlarının Yayılımı')
    _, a, b = item(114)
    rws = dx.spans(xml, 'tr', a, b)
    jobs = []
    for k, lab in enumerate(['Hedef Kitle', 'Hedefler ve Beklenen Kazanımlar',
                             'Kullanılacak Araçlar', 'Zamanlama']):
        body = [fields[lab]]
        if lab == 'Kullanılacak Araçlar':
            body += [[(f'{flat(r[0])}; paydaş: {flat(r[1])}; zaman: {flat(r[2])}.', False)] for r in yay]
        jobs.append((dx.spans(xml, 'tc', *rws[k])[0], body))
    for (ca, cb), pr in sorted(jobs, key=lambda j: -j[0][0]):
        xml = dx.fill_cell(xml, ca, cb, pr, keep=1)

    diger = m.paras(r'\section*{BELİRTMEK İSTEDİĞİNİZ DİĞER KONULAR}', r'\section*{EK-1: KAYNAKLAR}')
    _, a, b = item(117 + 4)
    ca, cb = dx.spans(xml, 'tc', a, b)[0]
    xml = dx.fill_cell(xml, ca, cb, diger)
    return xml, len(olanak), len(cikti), len(etki), len(yay), len(diger)


# ---------------------------------------------------------------------- figures

def _drawing(rid, w_cm, h_cm, name, idx):
    cx, cy = int(w_cm * CM), int(h_cm * CM)
    A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    return (f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{900+idx}" name="Şekil {idx}"/><wp:cNvGraphicFramePr>'
            f'<a:graphicFrameLocks xmlns:a="{A}" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            f'<a:graphic xmlns:a="{A}"><a:graphicData uri="http://schemas.openxmlformats.org/'
            f'drawingml/2006/picture"><pic:pic xmlns:pic="http://schemas.openxmlformats.org/'
            f'drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{900+idx}" name="{name}"/>'
            f'<pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/>'
            f'<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr>'
            f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            f'</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def captions(m: Manuscript):
    out = {}
    for mm in re.finditer(r'\\includegraphics\[[^\]]*\]\{figures/([^}]+)\}', m.tex):
        c = m.tex.index(r'\caption{', mm.end()) + len(r'\caption{')
        d, j = 1, c
        while d:
            d += {'{': 1, '}': -1}.get(m.tex[j], 0)
            j += 1
        out[mm.group(1)] = m.tex[c:j - 1]
    return out


def place_figures(m, xml, rels, ct, figdir):
    """Insert the figures into `xml`, returning it with the rels, types and media."""
    caps = captions(m)
    if 'Extension="png"' not in ct:
        ct = re.sub(r'(<Types[^>]*>)', r'\1<Default Extension="png" ContentType="image/png"/>',
                    ct, count=1)
    media, blocks = {}, []
    rpr = ('<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
           '<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>')
    for fname, item_idx, after, num in FIG_PLACE:
        rid = f'rIdFig{num}'
        rels = rels.replace('</Relationships>',
                            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
                            f'officeDocument/2006/relationships/image" Target="media/{fname}"/>'
                            f'</Relationships>')
        media[f'word/media/{fname}'] = (Path(figdir) / fname).read_bytes()
        cap = ('<w:p><w:pPr><w:jc w:val="both"/></w:pPr>'
               + dx.runs_xml([(f'Şekil {num}. ', True)] + rich(caps[fname]), rpr) + '</w:p>')
        blocks.append((item_idx, after, _drawing(rid, *FIG_CM[fname], fname, num) + cap, num))
    for item_idx, after, block, num in sorted(
            blocks, key=lambda z: (-z[0], -(z[1] if z[1] is not None else 999))):
        _, a, b = dx.body_items(xml)[item_idx]
        ca, cb = dx.spans(xml, 'tc', a, b)[0]
        ps = list(re.finditer(r'<w:p\b.*?</w:p>|<w:p\b[^>]*/>', xml[ca:cb], re.S))
        at = ca + (ps[after].end() if after is not None else ps[-1].end())
        xml = xml[:at] + block + xml[at:]
    return xml, rels, ct, media, len(blocks)


def write_docx(blank, out, xml, rels, ct, media):
    """One write, one handle: NFS refuses a rename onto a file another process holds."""
    with zipfile.ZipFile(blank) as zin, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zo:
        swap = {'word/document.xml': xml, 'word/_rels/document.xml.rels': rels,
                '[Content_Types].xml': ct}
        for it in zin.infolist():
            zo.writestr(it, swap[it.filename].encode('utf-8')
                        if it.filename in swap else zin.read(it.filename))
        for name, data in media.items():
            zo.writestr(name, data)


# -------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[3])
    ap.add_argument('--vault', required=True)
    ap.add_argument('--project', required=True)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    proj = Path(a.vault) / 'projects' / a.project
    blank = proj / 'archive/docs/bos_basvuru_formlari/1001_basvuru_formu.docx'
    out = Path(a.out) if a.out else proj / 'archive/docs/1001_BASVURU_FORMU_v3.docx'
    if not blank.exists():
        raise SystemExit(f'blank form not found: {blank}\n'
                         'Save TÜBİTAK\'s .doc as .docx in Word, unchanged, and put it there.')

    m = Manuscript(proj / 'manuscript.tex')
    xml = dx.load(blank)
    items = dx.body_items(xml)
    for (ca, cb), paras, keep, label in sorted(stage_text(m, xml, items), key=lambda j: -j[0][0]):
        xml = dx.fill_cell(xml, ca, cb, paras, keep=keep, force_body=label in BODY_CELLS)
        print(f'  {label}: {len(paras)} paragraf')

    xml, n_ip, plan = stage_packages(m, xml)
    print(f'  İş Paketi Tabloları: {n_ip}')
    for no, name, w, who, months in plan:
        print(f'  İş-Zaman İP{no}: Ay {min(months)}-{max(months)}, %{w}, {who}')

    xml, n_ol, n_ci, n_et, n_ya, n_dg = stage_impact(m, xml)
    print(f'  3.2: {n_ol} satır | 4.1: {n_ci} satır | 4.2: {n_et} etki | '
          f'4.3: {n_ya} etkinlik | Diğer: {n_dg} paragraf')

    z = zipfile.ZipFile(blank)
    rels = z.read('word/_rels/document.xml.rels').decode('utf-8')
    ct = z.read('[Content_Types].xml').decode('utf-8')
    z.close()
    xml, rels, ct, media, n_fig = place_figures(m, xml, rels, ct, proj / 'figures')
    write_docx(blank, out, xml, rels, ct, media)
    print(f'  Şekil: {n_fig}')

    kept = sum(1 for p in dx.paragraph_texts(dx.load(blank))
               if p and any(p in q for q in dx.paragraph_texts(dx.load(out))))
    total = sum(1 for p in dx.paragraph_texts(dx.load(blank)) if p)
    print(f'  şablonun kendi paragrafları: {kept}/{total} korundu')
    print('yazıldı:', out)


if __name__ == '__main__':
    main()
