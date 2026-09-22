#!/usr/bin/env python3
"""Check every numbered reference of a manuscript against Crossref (+ OpenAlex affiliations).

    pdftotext -layout submission.pdf ms.txt
    python <neuresearch>/src/verify_refs.py review/ms.txt review/refs_check.tsv [--email you@host]

Splits the list after a line "References", queries Crossref query.bibliographic for each
entry, and writes one TSV row per reference: claimed text vs. matched title/author/year/
journal/volume/page/DOI, title similarity, and the matched paper's institutions (for the
self-citation check). A low title_sim is a lead to open by hand, not a verdict: famous arXiv
papers (Mamba, S4) often top-match a look-alike. Stdlib only.
"""
import argparse, json, re, time, urllib.parse, urllib.request
from difflib import SequenceMatcher
from pathlib import Path


def get(url, ua):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == 3:
                raise
            time.sleep(2 ** i)


def split_refs(text):
    body = re.split(r"\n\s*References\s*\n", text, maxsplit=1)[1]
    body = re.sub(r"\n[^\n]*(Preprint submitted|Page \d+ of \d+)[^\n]*", "\n", body)
    parts = re.split(r"\n\s*\[(\d+)\]\s+", "\n" + body)
    return {int(parts[i]): " ".join(parts[i + 1].split()) for i in range(1, len(parts), 2)}


def sim(a, b):
    n = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower())
    return round(SequenceMatcher(None, n(a), n(b)).ratio(), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ms_txt"); ap.add_argument("out_tsv"); ap.add_argument("--email", default="anonymous@example.org")
    a = ap.parse_args()
    ua = {"User-Agent": f"reviewing-manuscripts refcheck (mailto:{a.email})"}
    refs = split_refs(Path(a.ms_txt).read_text())
    cols = "n score title_sim doi claimed found_first_author found_year found_journal found_vol found_page found_title affiliations"
    rows = [cols.replace(" ", "\t")]
    for n, ref in sorted(refs.items()):
        m = re.match(r"(.+?), (\d{4})[a-z]?\. (.+?)\. ", ref)
        items = get(f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(ref)}&rows=1", ua)["message"]["items"]
        if not items:
            rows.append(f"{n}\t\t\t\t{ref}\tNO MATCH"); continue
        it = items[0]
        title = (it.get("title") or [""])[0]
        try:
            oa = get(f"https://api.openalex.org/works/doi:{urllib.parse.quote(it['DOI'])}", ua)
            affs = sorted({i["display_name"] for x in oa["authorships"] for i in x.get("institutions", [])})
        except Exception:
            affs = ["(openalex miss)"]
        rows.append("\t".join(map(str, [
            n, round(it.get("score", 0)), sim(m.group(3) if m else ref, title), it["DOI"], ref,
            (it.get("author") or [{}])[0].get("family", ""), (it.get("issued", {}).get("date-parts") or [[None]])[0][0],
            (it.get("container-title") or [""])[0], it.get("volume", ""), it.get("page", it.get("article-number", "")),
            title, "; ".join(affs)])))
        time.sleep(0.3)
    Path(a.out_tsv).write_text("\n".join(rows) + "\n")
    print(f"{len(refs)} refs -> {a.out_tsv}")


if __name__ == "__main__":
    main()
