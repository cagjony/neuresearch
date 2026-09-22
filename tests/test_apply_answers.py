"""apply_answers: strike keeps the text visible; heading_after/para_after inherit spacing."""
import subprocess, sys, zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src' / 'apply_answers.py'
BODY = ('<w:p><w:pPr><w:spacing w:after="120"/><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr>'
        '<w:r><w:t>Old criterion one. Keep this.</w:t></w:r></w:p>')


def make_docx(p: Path) -> None:
    doc = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w='
           '"http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + BODY + '</w:body></w:document>')
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('word/document.xml', doc)


def test_strike_and_heading(tmp_path: Path) -> None:
    src, out, ans = tmp_path / 'in.docx', tmp_path / 'out.docx', tmp_path / 'a.md'
    make_docx(src)
    ans.write_text('## at=Keep this.\ntype: para_after\ntext: Body.\n\n'
                   '## at=Keep this.\ntype: heading_after\ntext: New section\n\n'
                   '## at=Keep this.\ntype: strike\nfind: Old criterion one.\n\n'
                   '## at=Keep this.\ntype: revise\nfind: Keep this.\ntext: Kept, reworded.\n\n'
                   '## at=Keep this.\ntype: insert_after\nfind: Old criterion\ntext:  [added]\n\n'
                   '## at=Body.\ntype: strike_block\n')
    subprocess.run([sys.executable, str(SRC), '--docx', str(src), '--answers', str(ans),
                    '--out', str(out)], check=True)
    doc = zipfile.ZipFile(out).read('word/document.xml').decode()
    assert 'Old criterion' in doc and ' one.' in doc and '<w:strike/>' in doc  # struck, not deleted
    assert doc.index('New section') < doc.index('Body.')                  # heading lands first
    assert '<w:b/>' in doc and doc.count('w:spacing w:after="120"') == 3  # spacing inherited
    assert doc.count('<w:numPr>') == 1                                    # numbering not copied
    assert doc.count('<w:strike/>') >= 2 and 'Kept, reworded.' in doc     # revise keeps the old
    assert doc.index('Old criterion') < doc.index('[added]') < doc.index('one.')
    body = doc[doc.rindex('<w:p>'):]                                       # the struck paragraph
    assert '<w:strike/>' in body and body.count('w:color') == 1
