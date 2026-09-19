#!/usr/bin/env python3
r"""
docx_comments.py — read a reviewed .docx back out.

    python docx_comments.py reviewed.docx                     # human-readable list
    python docx_comments.py reviewed.docx --answers > ans.md  # answers-file skeleton

The return leg of the review loop. A .docx goes out (tex2docx.py), someone comments
and edits it in Word, it lands in `archive/docs/`, and this reads it back: every
comment with the text it is anchored to, plus every tracked insertion and deletion.

With `--answers` it emits an ANSWERS_FORMAT.md skeleton — one `## id=<n>` block per
comment, with `find:` prefilled from the anchored text — so the edits can be authored
against the .tex instead of retyped. Blocks come out as `type: TODO`; you decide what
each becomes and delete the ones that need no edit. Nothing is auto-resolved: a comment
is closed only by a person writing `resolve: yes`.

Requires: Python 3.9+, stdlib only. Opens the file read-only.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def text_of(el) -> str:
    """Visible text of an element, skipping deleted runs."""
    out = []
    for node in el.iter():
        if node.tag == f"{W}delText":
            continue
        if node.tag == f"{W}t" and node.text:
            out.append(node.text)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def load_comments(z: zipfile.ZipFile) -> dict[str, dict]:
    try:
        root = ET.fromstring(z.read("word/comments.xml"))
    except KeyError:
        return {}
    out = {}
    for c in root.findall(f"{W}comment"):
        cid = c.get(f"{W}id")
        out[cid] = {
            "id": cid,
            "author": c.get(f"{W}author", "").strip(),
            "date": (c.get(f"{W}date") or "")[:10],
            "text": text_of(c),
            "anchor": "",
        }
    return out


def anchor_text(z: zipfile.ZipFile, comments: dict) -> None:
    """Fill each comment's anchor: the document text between its range markers."""
    xml = z.read("word/document.xml").decode("utf8", "ignore")
    for cid in comments:
        m = re.search(
            r'<w:commentRangeStart[^>]*w:id="%s"[^>]*/>(.*?)<w:commentRangeEnd[^>]*w:id="%s"'
            % (re.escape(cid), re.escape(cid)), xml, re.S)
        if not m:
            continue
        frag = m.group(1)
        frag = re.sub(r"<w:delText[^>]*>.*?</w:delText>", "", frag, flags=re.S)
        txt = " ".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", frag, re.S))
        comments[cid]["anchor"] = re.sub(r"\s+", " ", txt).strip()


def tracked_changes(z: zipfile.ZipFile) -> list[dict]:
    root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for tag, kind in ((f"{W}ins", "inserted"), (f"{W}del", "deleted")):
        for el in root.iter(tag):
            if kind == "deleted":
                t = "".join(n.text or "" for n in el.iter(f"{W}delText"))
            else:
                t = "".join(n.text or "" for n in el.iter(f"{W}t"))
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                out.append({"kind": kind, "author": el.get(f"{W}author", "").strip(),
                            "date": (el.get(f"{W}date") or "")[:10], "text": t})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--answers", action="store_true",
                    help="emit an answers-file skeleton instead of a report")
    a = ap.parse_args()
    if not a.docx.exists():
        sys.exit(f"no such file: {a.docx}")

    with zipfile.ZipFile(a.docx) as z:
        comments = load_comments(z)
        anchor_text(z, comments)
        changes = tracked_changes(z)

    order = sorted(comments.values(), key=lambda c: int(c["id"]) if c["id"].isdigit() else 0)

    if a.answers:
        print(f"<!-- Skeleton from {a.docx.name}. The .tex is the source of truth: author each")
        print("     edit here, then apply it to the .tex. `type: TODO` means undecided —")
        print("     every block needs a real type or deleting. Nothing is auto-resolved;")
        print("     a comment waiting on a fact we do not have STAYS, with no edit. -->")
        for c in order:
            print(f"\n## id={c['id']}")
            print(f"# {c['author']}: {c['text']}")
            print("type: TODO")
            if c["anchor"]:
                print(f"find: {c['anchor']}")
            print("text: ")
        return

    print(f"  {a.docx.name}")
    print(f"  {len(comments)} comments · {len(changes)} tracked changes")
    if comments:
        who = {}
        for c in order:
            who[c["author"]] = who.get(c["author"], 0) + 1
        print("  by author: " + ", ".join(f"{k or '(unnamed)'} {v}" for k, v in who.items()))
        print()
        for c in order:
            print(f"  [{c['id']}] {c['author']} {c['date']}")
            if c["anchor"]:
                s = c["anchor"]
                print(f"       on: \"{s[:110]}{'…' if len(s) > 110 else ''}\"")
            print(f"       says: {c['text']}")
    if changes:
        print(f"\n  tracked changes:")
        for ch in changes[:40]:
            s = ch["text"]
            print(f"    {ch['kind']:<8} {ch['author'] or '(unnamed)'}: "
                  f"{s[:90]}{'…' if len(s) > 90 else ''}")
        if len(changes) > 40:
            print(f"    … and {len(changes)-40} more")


if __name__ == "__main__":
    main()
