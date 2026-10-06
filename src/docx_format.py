"""Give a pandoc .docx the shape a journal asks for: A4, margins, double
spacing, page numbers.

Pandoc's default .docx is US Letter, single-spaced and carries no page numbers,
which no journal accepts. Two steps fix it, and both are needed:

  make_reference_docx()  patches pandoc's own default reference.docx -- this
                         sets the STYLES (line spacing, page setup defaults)
                         that pandoc then writes the document against.
  finalize()             patches the written file -- pandoc 2.7 emits no
                         <w:sectPr> at all, so Word silently falls back to
                         Letter however the reference doc was set up, and the
                         page-number field has to be added as a real footer
                         part with its relationship and content-type entries.

This was first written inline in neubrain/projects/alz-olf/anatomy/build.py for
the Anatomy submission. It is here because deep-sniff needed the same thing;
alz-olf still carries its own copy because that submission is finished and not
worth disturbing. A third caller should make alz-olf import this one.

    python src/docx_format.py --selftest
"""
import re, subprocess, zipfile
from pathlib import Path

A4 = (11906, 16838)          # twips, 210 x 297 mm
MARGIN_25MM = 1418           # twips
DOUBLE = 480                 # w:line, twentieths of a point -> double spacing

_FOOTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
           '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
           '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
           '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
           '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')
_FTR_REL = ('<Relationship Id="rIdFtrPage" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/footer" Target="footer_page.xml"/>')
_FTR_CT = ('<Override PartName="/word/footer_page.xml" ContentType="application/'
           'vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>')


def _pgsetup(pgsz, margin):
    return (f'<w:pgSz w:w="{pgsz[0]}" w:h="{pgsz[1]}"/>'
            f'<w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" '
            f'w:left="{margin}" w:header="709" w:footer="709" w:gutter="0"/>')


def make_reference_docx(path, line=DOUBLE, pgsz=A4, margin=MARGIN_25MM,
                        extra_styles=""):
    """Write pandoc's default reference.docx with spacing and page setup applied."""
    path = Path(path)
    raw = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"],
                         check=True, capture_output=True).stdout
    tmp = path.with_suffix(".tmp.docx"); tmp.write_bytes(raw)
    with zipfile.ZipFile(tmp) as zin, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                s = data.decode("utf-8")
                s = re.sub(r"<w:pPrDefault>.*?</w:pPrDefault>",
                           '<w:pPrDefault><w:pPr><w:spacing w:after="0" '
                           f'w:line="{line}" w:lineRule="auto"/></w:pPr></w:pPrDefault>',
                           s, count=1, flags=re.S)
                s = re.sub(r"<w:spacing [^>]*/>",
                           f'<w:spacing w:before="0" w:after="0" w:line="{line}" '
                           'w:lineRule="auto"/>', s)
                if extra_styles:
                    s = s.replace("</w:styles>", extra_styles + "</w:styles>")
                data = s.encode("utf-8")
            elif item.filename == "word/document.xml":
                s = data.decode("utf-8")
                s = re.sub(r"<w:pgSz[^>]*/>", _pgsetup(pgsz, margin).split("<w:pgMar")[0], s)
                s = re.sub(r"<w:pgMar[^>]*/>",
                           "<w:pgMar" + _pgsetup(pgsz, margin).split("<w:pgMar")[1], s)
                data = s.encode("utf-8")
            zout.writestr(item, data)
    tmp.unlink()
    return path


def finalize(docx, page_numbers=True, pgsz=A4, margin=MARGIN_25MM):
    """Force the section properties onto a written .docx, optionally with a
    centred PAGE field in the footer."""
    docx = Path(docx)
    ftr = ('<w:footerReference xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
           '2006/relationships" w:type="default" r:id="rIdFtrPage"/>') if page_numbers else ""
    sect = f"<w:sectPr>{ftr}{_pgsetup(pgsz, margin)}</w:sectPr>"
    tmp = docx.with_suffix(".tmp")
    with zipfile.ZipFile(docx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                s = re.sub(r"<w:sectPr.*?</w:sectPr>|<w:sectPr\s*/>", "",
                           data.decode("utf-8"), flags=re.S)
                data = s.replace("</w:body>", sect + "</w:body>").encode("utf-8")
            elif page_numbers and item.filename == "word/_rels/document.xml.rels":
                data = data.decode("utf-8").replace(
                    "</Relationships>", _FTR_REL + "</Relationships>").encode("utf-8")
            elif page_numbers and item.filename == "[Content_Types].xml":
                data = data.decode("utf-8").replace(
                    "</Types>", _FTR_CT + "</Types>").encode("utf-8")
            zout.writestr(item, data)
        if page_numbers:
            zout.writestr("word/footer_page.xml", _FOOTER)
    tmp.replace(docx)
    return docx


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ref = make_reference_docx(d / "reference.docx")
        with zipfile.ZipFile(ref) as z:
            st = z.read("word/styles.xml").decode()
        assert f'w:line="{DOUBLE}"' in st, "spacing not applied to the reference doc"

        (d / "in.md").write_text("# Title\n\nOne paragraph.\n")
        subprocess.run(["pandoc", str(d / "in.md"), "-o", str(d / "out.docx"),
                        "--reference-doc", str(ref)], check=True)
        finalize(d / "out.docx")
        with zipfile.ZipFile(d / "out.docx") as z:
            names, doc = z.namelist(), z.read("word/document.xml").decode()
            assert "word/footer_page.xml" in names, "footer part missing"
            assert f'w:w="{A4[0]}"' in doc, "A4 page size missing"
            assert doc.count("<w:sectPr>") == 1, "exactly one sectPr expected"
            assert _FTR_CT.split('PartName="')[1][:20] in z.read("[Content_Types].xml").decode()
    print("docx_format selftest OK: A4, double spacing, one sectPr, page-number footer")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
