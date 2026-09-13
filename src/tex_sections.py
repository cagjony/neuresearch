#!/usr/bin/env python3
r"""
tex_sections.py
===============
Read a LaTeX manuscript as the content of a form.

The proposal is written and revised in one place, `manuscript.tex`. The form is
a rendering of it. This module turns that file into what a .docx cell needs:
plain paragraphs, each a list of (text, bold) runs, plus the table rows and the
work-package blocks the form asks for as structured fields.

    m = Manuscript('…/manuscript.tex')
    m.paras(r'\subsection{Amaç ve Hedefler}', r'\section{YÖNTEM}')
    m.rows(r'\textbf{Projede Kullanım Amacı}\\', r'\end{tabularx}', 3)
    m.packages(); m.risks()

Used by fill_1001_form.py. Stdlib only.
"""

import re

_SYMBOLS = [
    ("$\\times$", "\u00d7"), ("$\\pm$", "\u00b1"), ("$\\geq$", "\u2265"),
    ("$\\leq$", "\u2264"), ("$\\rightarrow$", "\u2192"), ("$\\leftrightarrow$", "\u2194"),
    ("$\\bullet$", "\u2022"), ("$\\delta$", "\u03b4"), ("$\\alpha$", "\u03b1"),
    ("$\\beta$", "\u03b2"), (r"\%", "%"), (r"\&", "&"), (r"\_", "_"),
    (r"\textmu{}", "\u00b5"), (r"\ldots{}", "\u2026"), ("``", "\u201c"), ("''", "\u201d"),
    ("R$^{2}$", "R\u00b2"),
]


def tex2txt(t):
    """One LaTeX fragment -> plain text, citations as [n] into EK-1's numbering."""
    t = re.sub(r"\\cite\{([^}]+)\}",
               lambda m: "[" + ",".join(str(n) for n in sorted(
                   int(x.strip().replace('ref', '')) for x in m.group(1).split(','))) + "]", t)
    for pat in (r"\\noindent\\textbf\{(.*?)\}", r"\\textbf\{(.*?)\}", r"\\emph\{(.*?)\}"):
        t = re.sub(pat, r"\1", t, flags=re.S)
    t = t.replace("\\ ", " ").replace("~", " ")
    for a, b in _SYMBOLS:
        t = t.replace(a, b)
    t = re.sub(r"\$(\d+)\^\{(\d+)\}\s*=\s*([\d.]+)\$",
               lambda m: m.group(1) + m.group(2).translate(str.maketrans("0123456789","\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")) + " = " + m.group(3), t)
    t = re.sub(r"\$\^\{(-?\d+)\}\$",
               lambda m: m.group(1).translate(str.maketrans("-0123456789", "\u207b\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")), t)
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", "", t)
    t = t.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip()


def rich(par):
    """One LaTeX paragraph -> [(text, bold), …], keeping \\textbf as bold runs."""
    par = re.sub(r'\\noindent\s*', '', par)
    par = re.sub(r'\\textbf\{((?:[^{}]|\{[^{}]*\})*)\}',
                 lambda m: '\x01' + m.group(1) + '\x02', par)
    out = []
    for i, chunk in enumerate(re.split(r'\x01|\x02', par)):
        txt = tex2txt(chunk)
        if txt:
            out.append((txt + ' ' if i % 2 else txt, i % 2 == 1))
    return out


def flat(runs):
    return ''.join(t for t, _ in runs)


class Manuscript:
    def __init__(self, path):
        self.path = path
        self.tex = open(path, encoding='utf-8').read()

    def raw(self, start, end):
        a = self.tex.index(start) + len(start)
        s = self.tex[a:self.tex.index(end, a)]
        return re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', '', s, flags=re.S)

    def paras(self, start, end):
        """Body paragraphs of a section, figures dropped."""
        out = []
        for p in self.raw(start, end).split('\n\n'):
            if p.strip() and (r := rich(p)):
                out.append(r)
        return out

    def rows(self, after, until, ncol):
        """Body rows of a LaTeX table, each a list of `ncol` rich cells."""
        s = self.tex[self.tex.index(after) + len(after):self.tex.index(until, self.tex.index(after))]
        s = re.sub(r'\\(addlinespace|midrule|toprule|bottomrule|endhead|endfirsthead)(\[[^\]]*\])?', '', s)
        out = []
        for line in s.split('\\\\'):
            cells = re.split(r'(?<!\\)&', line)
            if len(cells) != ncol or '\\textbf{' in cells[0]:
                continue    # a repeated longtable header (\endhead), not a row
            out.append([rich(c) for c in cells])
        return out

    def packages(self):
        """The İş Paketi description blocks as {field label: LaTeX}."""
        out = []
        for b in re.findall(r'\\begin\{description\}(.*?)\\end\{description\}', self.tex, re.S):
            if r'\item[İP No:]' not in b:
                continue
            fields, cur = {}, None
            for piece in re.split(r'\\item\[([^\]]+)\]', b)[1:]:
                if cur is None:
                    cur = piece
                else:
                    fields[cur], cur = piece.strip(), None
            out.append(fields)
        return out

    def risks(self):
        """(İP, risk, mitigation) from the risk longtable."""
        t = self.tex[self.tex.index(r'\textbf{İP No} & \textbf{Risk(ler)in Tanımı}'):
                     self.tex.index(r'\end{longtable}')]
        return [(ip, flat(rich(c[0])), flat(rich(c[1])))
                for ip, rest in re.findall(r'^(İP\d) & (.*?)\\\\$', t, re.M | re.S)
                for c in [re.split(r'(?<!\\)&', rest)]]

    def description(self, after):
        """A description list after `after`, as {label: rich runs}."""
        d = re.search(r'\\begin\{description\}(.*?)\\end\{description\}',
                      self.tex[self.tex.index(after):], re.S).group(1)
        parts = re.split(r'\\item\[([^\]]+)\]', d)[1:]
        return {k.rstrip(':'): rich(v.strip()) for k, v in zip(parts[::2], parts[1::2])}
