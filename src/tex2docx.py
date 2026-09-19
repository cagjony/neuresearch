#!/usr/bin/env python3
r"""
tex2docx.py — make a Word review copy of a LaTeX manuscript.

    python tex2docx.py --tex manuscript.tex --out review/manuscript_review.docx

THE .TEX STAYS THE SOURCE OF TRUTH. The .docx produced here is a READ-ONLY review
copy — for reading the story end to end, and for collecting comments from people who
work in Word. Edits never travel back by hand: comments come back as an answers file
(see neuresearch/ANSWERS_FORMAT.md) that is applied to the .tex.

Why a preprocessing pass: Elsevier's cas-sc class has environments pandoc does not
know (`highlights`, `keywords`, `graphicalabstract`), and it silently DROPS them —
so a straight `pandoc manuscript.tex` loses the highlights entirely. Each is rewritten
into something pandoc understands before conversion.

Known limits, stated rather than hidden:
  * display math converts to OMML only for simple expressions; anything with \frac,
    \mathcal, matrices etc. is left as literal TeX. Fine for reading the argument,
    not for checking equations — check those in the PDF.
  * figures are embedded at their .png resolution; captions survive.

Requires: pandoc (>= 2.7) and pandoc-citeproc on PATH. Python 3.9+, stdlib only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def unwrap(body: str, env: str, repl) -> str:
    """Replace \begin{env}...\end{env} using repl(inner) -> str."""
    pat = re.compile(r"\\begin\{" + env + r"\}(.*?)\\end\{" + env + r"\}", re.S)
    return pat.sub(lambda m: repl(m.group(1)), body)


def preprocess(tex: str) -> str:
    # cas-sc frontmatter wrappers pandoc does not recognise
    tex = unwrap(tex, "frontmatter", lambda s: s)

    # highlights -> a real section with a bullet list (otherwise silently dropped)
    tex = unwrap(tex, "highlights",
                 lambda s: "\\section*{Highlights}\n\\begin{itemize}\n" + s.strip()
                           + "\n\\end{itemize}\n")

    # keywords -> a section; cas-sc separates entries with \sep
    tex = unwrap(tex, "keywords",
                 lambda s: "\\section*{Keywords}\n"
                           + ", ".join(w.strip() for w in s.split("\\sep") if w.strip())
                           + "\n")

    # the graphical abstract is a figure for the journal, noise in a reading copy
    tex = unwrap(tex, "graphicalabstract", lambda s: "")

    # cas-sc author/affiliation markup carries no meaning in Word
    for cmd in ("cortext", "fnmark", "cormark", "tnotemark", "tnotetext", "fntext",
                "nonumnote", "printcredits"):
        tex = re.sub(r"\\" + cmd + r"(\[[^\]]*\])?(\{[^{}]*\})?", "", tex)

    # keep \ref/\label working as plain text rather than vanishing
    tex = re.sub(r"~?\\ref\{fig:([^}]*)\}", r" (see figure: \1)", tex)
    tex = re.sub(r"~?\\ref\{app:([^}]*)\}", r" (see appendix: \1)", tex)
    tex = re.sub(r"~?\\ref\{tab:([^}]*)\}", r" (see table: \1)", tex)
    return tex


def convert(tex_path: Path, out: Path, bib: Path | None, toc: bool) -> None:
    src = tex_path.read_text(encoding="utf-8")
    body = preprocess(src)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / tex_path.name
        tmp.write_text(body, encoding="utf-8")
        cmd = ["pandoc", str(tmp), "-o", str(out),
               "--resource-path", str(tex_path.parent),
               "--metadata", "reference-section-title=References",
               "--wrap=preserve"]
        if toc:
            cmd += ["--toc", "--toc-depth=2"]
        if bib and bib.exists():
            cmd += ["--filter", "pandoc-citeproc", f"--bibliography={bib}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        warns = [l for l in r.stderr.splitlines() if "Could not convert TeX math" not in l]
        n_math = sum("Could not convert TeX math" in l for l in r.stderr.splitlines())
        if r.returncode != 0:
            sys.exit("pandoc failed:\n" + r.stderr)
        for w in warns[:10]:
            print("  " + w)
        if n_math:
            print(f"  {n_math} math expressions left as literal TeX "
                  f"(pandoc cannot render them; check equations in the PDF)")


def report(out: Path) -> None:
    import zipfile
    z = zipfile.ZipFile(out)
    x = z.read("word/document.xml").decode("utf8", "ignore")
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))
    imgs = [n for n in z.namelist() if n.startswith("word/media/")]
    print(f"\n  wrote {out}  ({out.stat().st_size/1024:.0f} KB)")
    print(f"    {len(txt.split()):,} words · {len(imgs)} figures · "
          f"{len(re.findall(chr(34) + 'Heading', x))} headings")
    for probe in ("Highlights", "Keywords", "References"):
        print(f"    {probe:<12} {'present' if probe in txt else 'MISSING'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--bib", type=Path, default=None,
                    help="default: references.bib next to the .tex")
    ap.add_argument("--toc", action="store_true", help="add a table of contents")
    a = ap.parse_args()
    if not shutil.which("pandoc"):
        sys.exit("pandoc not found on PATH")
    bib = a.bib or (a.tex.parent / "references.bib")
    convert(a.tex, a.out, bib, a.toc)
    report(a.out)


if __name__ == "__main__":
    main()
