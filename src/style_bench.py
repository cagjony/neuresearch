#!/usr/bin/env python3
"""Benchmark a draft's prose against highly cited exemplar papers in the vault.

Three subcommands:

  corpus    pick exemplars from _library/*.xml (research articles in top journals
            with high citations per year) and measure their prose per section.
            Writes logs/style-corpus.json + logs/style-corpus.md (generated).
  check     measure a draft (.md or .tex) the same way and report where it sits
            in the exemplar distribution, which words it over-uses relative to
            the exemplars, and every sentence carrying a known machine-prose tell.
            Writes <draft dir>/style-report.md (report-only; never edits the draft).
  passages  print exemplar paragraphs of one section, for side-by-side reading.

Numbers are flags, not verdicts: a sentence-length percentile cannot tell good
prose from bad. The scientific-writing and exemplar-style skills say how to read them.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date
from pathlib import Path

SECTIONS = ("abstract", "intro", "results", "discussion")
SECTION_KEYS = {  # first match wins, tested against a lower-cased heading
    "abstract": ("abstract", "summary"),
    "intro": ("introduction", "intro", "background"),
    "results": ("result",),
    "discussion": ("discussion", "conclusion"),
}
# Journals whose prose counts as an exemplar. Lower-case, exact after normalising.
TOP_JOURNALS = {
    "nature", "science", "science (new york, n.y.)", "cell", "neuron",
    "nature neuroscience", "nature methods", "nature communications", "elife",
    "plos biology", "current biology", "nature human behaviour",
    "proceedings of the national academy of sciences of the united states of america",
    "the journal of neuroscience", "journal of neuroscience", "cell reports",
}
SKIP_TAGS = {"xref", "fig", "table-wrap", "disp-formula", "inline-formula", "label",
             "supplementary-material", "ext-link"}
# Machine-prose tells: words and phrases LLM text over-uses. Their exemplar rate is
# measured, so a word real papers use often (e.g. "robust") is only flagged when a
# draft uses it far more than the exemplars do.
TELLS = [
    "delve", "delves", "crucial", "crucially", "pivotal", "underscore", "underscores",
    "underscoring", "highlight", "highlights", "highlighting", "notably", "furthermore",
    "moreover", "additionally", "intricate", "comprehensive", "robust", "landscape",
    "realm", "tapestry", "multifaceted", "nuanced", "leverage", "leveraging", "novel",
    "seamless", "seamlessly", "holistic", "elucidate", "elucidating", "foster",
    "showcase", "showcases", "groundbreaking", "remarkable", "remarkably", "paramount",
    "intriguing", "intriguingly", "unveil", "unveils", "unravel", "harness", "harnessing",
    "interplay", "nuance", "noteworthy", "importantly", "interestingly", "overall",
    "shed light", "sheds light", "pave the way", "paving the way", "plays a crucial role",
    "plays a key role", "plays a pivotal role", "it is important to note",
    "it is worth noting", "in conclusion", "taken together", "a wide range of",
    "in the context of", "not only", "serves as", "in summary",
]
HEDGES = {"may", "might", "could", "suggest", "suggests", "suggesting", "possibly",
          "potentially", "likely", "perhaps", "appear", "appears", "seem", "seems"}
SELF_PRAISE = {"interesting", "important", "novel", "understudied", "unprecedented",
               "remarkable", "striking", "powerful"}
BE = {"is", "are", "was", "were", "be", "been", "being"}
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
ABBREV = re.compile(r"\b(?:et al|e\.g|i\.e|Fig|Figs|Eq|Ref|vs|approx|ca|cf|Suppl|Ext|No)\.", re.I)
SENT_END = re.compile(r"(?<=[.?!])\s+(?=[\"'(\[]?[A-Z0-9])")
HIGH_ONLY = {"tell_rate", "self_praise_rate", "dash_rate"}  # fewer is never a problem
METRICS = {  # name -> (label, unit)
    "sent_len_median": ("sentence length, median", "words"),
    "sent_len_cv": ("sentence-length variation (CV)", ""),
    "para_len_median": ("paragraph length, median", "words"),
    "we_rate": ("'we'", "/100 words"),
    "passive_rate": ("passive-voice sentences", "%"),
    "hedge_rate": ("hedges", "/1000 words"),
    "nominal_rate": ("nominalisations (-tion/-ment/-ance/-ence)", "/100 words"),
    "dash_rate": ("em/en dashes", "/1000 words"),
    "transition_open_rate": ("sentences opening on a connective", "%"),
    "tell_rate": ("machine-prose tells", "/1000 words"),
    "self_praise_rate": ("self-praise adjectives", "/1000 words"),
}


# --------------------------------------------------------------------------- #
# text -> metrics
# --------------------------------------------------------------------------- #
def sentences(text: str) -> list[str]:
    protected = ABBREV.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    protected = re.sub(r"(\d)\.(\d)", "\\1\x00\\2", protected)
    return [s.replace("\x00", ".").strip() for s in SENT_END.split(protected) if s.strip()]


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text)]


def tell_hits(text: str) -> list[str]:
    low = " " + " ".join(words(text)) + " "
    return [t for t in TELLS for _ in range(low.count(f" {t} "))]


def measure(paragraphs: list[str]) -> dict | None:
    """Prose metrics of one section; None when it is too short to mean anything."""
    sents = [s for p in paragraphs for s in sentences(p)]
    ws = [w for p in paragraphs for w in words(p)]
    n = len(ws)
    if n < 150 or len(sents) < 5:
        return None
    lens = [len(words(s)) for s in sents]
    passive = sum(bool(re.search(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b", s, re.I))
                  for s in sents)
    opener = sum(bool(re.match(r"(?:however|moreover|furthermore|additionally|notably|importantly|"
                               r"interestingly|consequently|thus|therefore|overall|together|"
                               r"in addition|taken together|in summary)\b,?", s, re.I)) for s in sents)
    text = " ".join(paragraphs)
    return {
        "words": n,
        "sent_len_median": statistics.median(lens),
        "sent_len_cv": statistics.pstdev(lens) / statistics.mean(lens),
        "para_len_median": statistics.median(len(words(p)) for p in paragraphs),
        "we_rate": 100 * sum(w in ("we", "our", "us") for w in ws) / n,
        "passive_rate": 100 * passive / len(sents),
        "hedge_rate": 1000 * sum(w in HEDGES for w in ws) / n,
        "nominal_rate": 100 * sum(len(w) > 6 and w.endswith(("tion", "tions", "ment", "ments", "ance", "ence"))
                                  for w in ws) / n,
        "dash_rate": 1000 * len(re.findall(r"—|(?<!\d)\s?–\s?(?!\d)|\s--?\s", text)) / n,  # not 50–100 µM
        "transition_open_rate": 100 * opener / len(sents),
        "tell_rate": 1000 * len(tell_hits(text)) / n,
        "self_praise_rate": 1000 * sum(w in SELF_PRAISE for w in ws) / n,
    }


def section_of(heading: str) -> str | None:
    h = re.sub(r"^[\d.\s]+", "", heading.lower()).strip()
    for sec, keys in SECTION_KEYS.items():
        if any(h.startswith(k) for k in keys):
            return sec
    return None


# --------------------------------------------------------------------------- #
# JATS
# --------------------------------------------------------------------------- #
def para_text(p: ET.Element) -> str:
    out = [p.text or ""]
    for c in p:
        if c.tag not in SKIP_TAGS:
            out.append(para_text(c))
        out.append(c.tail or "")
    t = "".join(out)
    t = re.sub(r"\(\s*[,;–\s]*\)|\[\s*[,;–\s]*\]", "", t)  # brackets emptied by dropped xrefs
    return re.sub(r"\s+", " ", t).strip()


def prose_ps(el: ET.Element):
    """Running-text <p> under el, skipping captions, tables and boxes."""
    for c in el:
        if c.tag == "p":
            yield c
        elif c.tag not in ("fig", "table-wrap", "boxed-text", "supplementary-material"):
            yield from prose_ps(c)


def jats_sections(root: ET.Element) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {s: [] for s in SECTIONS}
    front = root.find("front")
    for ab in (front.iter("abstract") if front is not None else []):
        if ab.get("abstract-type") in (None, "", "summary") and not out["abstract"]:
            out["abstract"] = [para_text(p) for p in ab.iter("p")]
    body = root.find("body")
    if body is None:
        return out
    out["intro"] += [para_text(p) for p in body.findall("p")]  # Nature-style untitled intro
    for sec in body.findall("sec"):
        name = section_of(sec.findtext("title") or "") or section_of(sec.get("sec-type") or "")
        if name:
            out[name] += [para_text(p) for p in prose_ps(sec)]
    return {k: [p for p in v if len(p.split()) >= 8] for k, v in out.items()}


def jats_meta(root: ET.Element) -> dict:
    meta = root.find("front/article-meta")
    doi = meta.findtext("article-id[@pub-id-type='doi']") if meta is not None else None
    years = [y.text for y in root.iter("year") if y.text and y.text.isdigit()]
    return {
        "type": root.get("article-type"),
        "journal": (root.findtext("front/journal-meta//journal-title") or "").strip(),
        "doi": (doi or "").lower().strip(),
        "title": " ".join("".join(root.find("front/article-meta/title-group/article-title").itertext()).split())
        if root.find("front/article-meta/title-group/article-title") is not None else "",
        "year": int(min(years)) if years else None,
    }


# --------------------------------------------------------------------------- #
# drafts
# --------------------------------------------------------------------------- #
def clean_markup(t: str) -> str:
    t = re.sub(r"\\begin\{(figure|table|equation|align)\*?\}.*?\\end\{\1\*?\}", " ", t, flags=re.S)
    t = re.sub(r"\[[^\]]*@[^\]]*\]|\\[a-z]*cite[a-z]*\*?(\[[^\]]*\])*\{[^}]*\}|\\ref\{[^}]*\}", "", t)
    t = re.sub(r"\\(?:emph|textit|textbf|mathrm|text)\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\$[^$]*\$", "X", t)
    t = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?", "", t).replace("~", " ").replace("{", "").replace("}", "")
    t = re.sub(r"[*_`]+|<!--.*?-->|!?\[[^\]]*\]\([^)]*\)", "", t, flags=re.S)
    t = re.sub(r"\(\s*[,;\s]*\)", "", t)
    return re.sub(r"[ \t]+", " ", t)


def draft_sections(path: Path) -> dict[str, list[tuple[int, str]]]:
    """{section: [(first line number, paragraph text)]} from a .md or .tex draft."""
    head = re.compile(r"^\s*(?:(#{1,3})\s+(.+)|\\((?:sub)*)section\*?\{(.+?)\})")
    abstract_env = re.compile(r"\\(begin|end)\{abstract\}")
    out: dict[str, list[tuple[int, str]]] = {s: [] for s in SECTIONS}
    cur, buf, start = None, [], 0

    def flush():
        if cur and buf:
            text = clean_markup(" ".join(buf)).strip()
            if len(text.split()) >= 8:
                out[cur].append((start, text))
        buf.clear()

    def level_title(m):
        return (len(m.group(1)), m.group(2)) if m.group(1) else (1 + len(m.group(3)) // 3, m.group(4))

    tex = path.suffix == ".tex"
    lines = path.read_text(encoding="utf-8").splitlines()
    # The paper's section level is the shallowest heading naming a known section;
    # deeper headings ("\subsection{Background}" inside Methods) never switch section.
    named = [level_title(m)[0] for m in map(head.match, lines) if m and section_of(level_title(m)[1])]
    sec_level = min(named, default=1)
    for i, line in enumerate(lines, 1):
        if tex:
            line = re.sub(r"(?<!\\)%.*", "", line)  # tex comment; in Markdown % is a percent sign
        m, a = head.match(line), abstract_env.search(line)
        if m or a:
            flush()
            if a:
                cur = "abstract" if a.group(1) == "begin" else None
            else:
                level, title = level_title(m)
                if level <= sec_level:
                    cur = section_of(title)
            continue
        if not line.strip():
            flush()
        else:
            if not buf:
                start = i
            buf.append(line.strip())
    flush()
    return out


# --------------------------------------------------------------------------- #
# corpus
# --------------------------------------------------------------------------- #
def citations(dois: list[str], cache_path: Path, email: str) -> dict[str, int]:
    import requests
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [d for d in dois if d not in cache]
    s = requests.Session()
    s.headers["User-Agent"] = f"neuresearch style_bench (mailto:{email})"
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        r = s.get("https://api.openalex.org/works", timeout=60, params={
            "filter": "doi:" + "|".join(chunk), "per-page": 50,
            "select": "doi,cited_by_count", "mailto": email})
        r.raise_for_status()
        for w in r.json()["results"]:
            cache[(w["doi"] or "").removeprefix("https://doi.org/").lower()] = w["cited_by_count"]
        for d in chunk:
            cache.setdefault(d, None)  # no OpenAlex record: a result, not an error
        time.sleep(0.2)
    cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    return cache


def cmd_corpus(a) -> int:
    vault = Path(a.vault)
    manifest = json.loads((vault / "_library/manifest.json").read_text())["entries"]
    papers = []
    for stem, e in sorted(manifest.items()):
        xml = next((f for f in e.get("files", []) if f.endswith(".xml")), None)
        if not xml or (e.get("projects") and set(e["projects"]) <= set(a.exclude_project)):
            continue  # off-field: every project it belongs to is excluded
        try:
            root = ET.parse(vault / "_library" / xml).getroot()
        except ET.ParseError as err:
            print(f"skip {stem}: unparseable XML ({err})", file=sys.stderr)
            continue
        meta = jats_meta(root)
        meta.update(stem=stem, projects=e.get("projects", []), doi=meta["doi"] or (e.get("doi") or "").lower(),
                    year=int(e["year"]) if str(e.get("year", "")).isdigit() else meta["year"])
        if meta["type"] != "research-article" or meta["journal"].lower() not in TOP_JOURNALS:
            continue
        secs = {k: measure(v) for k, v in jats_sections(root).items()}
        if not (secs["intro"] and secs["results"] and secs["discussion"]):
            continue  # a merged "Results and Discussion" or no prose body: not a comparable shape
        papers.append({**meta, "sections": secs})
    cites = citations([p["doi"] for p in papers if p["doi"]], vault / "logs/style-citations.json", a.email)
    this_year = date.today().year
    for p in papers:
        c = cites.get(p["doi"])
        p["cited_by"] = c
        p["cites_per_year"] = round(c / max(1, this_year - (p["year"] or this_year) + 1), 1) if c is not None else None
    keep = [p for p in papers if (p["cites_per_year"] or 0) >= a.min_cites_per_year]
    keep.sort(key=lambda p: -p["cites_per_year"])
    vocab = {s: Counter() for s in SECTIONS}
    for p in keep:
        root = ET.parse(vault / "_library" / f"{p['stem']}.xml").getroot()
        for s, paras in jats_sections(root).items():
            vocab[s].update(words(" ".join(paras)))
    stats = {s: {m: pct([p["sections"][s][m] for p in keep if p["sections"][s]]) for m in METRICS}
             for s in SECTIONS}
    out = {"built": date.today().isoformat(), "min_cites_per_year": a.min_cites_per_year,
           "papers": keep, "stats": stats,
           "vocab": {s: dict(c.most_common(20000)) for s, c in vocab.items()}}
    (vault / "logs/style-corpus.json").write_text(json.dumps(out) + "\n")
    lines = [f"# Style corpus — exemplar papers ({len(keep)})", "",
             f"Generated by `style_bench.py corpus` on {out['built']}. Never hand-edit. "
             f"Research articles in top journals with ≥ {a.min_cites_per_year} citations/year "
             f"(OpenAlex) and separate Introduction, Results and Discussion. "
             f"{len(papers) - len(keep)} candidates fell below the citation floor. "
             f"Excluded projects: {', '.join(a.exclude_project) or 'none'}.", "",
             "| stem | journal | year | cites/yr | title |", "|---|---|---|---|---|"]
    lines += [f"| [[{p['stem']}]] | {p['journal']} | {p['year']} | {p['cites_per_year']} | {p['title'][:90]} |"
              for p in keep]
    (vault / "logs/style-corpus.md").write_text("\n".join(lines) + "\n")
    print(f"{len(keep)} exemplars (of {len(papers)} candidates) -> logs/style-corpus.{{json,md}}")
    return 0


def pct(xs: list[float]) -> dict | None:
    if len(xs) < 5:
        return None
    q = statistics.quantiles(xs, n=10)
    return {"n": len(xs), "p10": q[0], "p25": statistics.quantiles(xs, n=4)[0],
            "p50": statistics.median(xs), "p75": statistics.quantiles(xs, n=4)[2], "p90": q[8]}


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def overused(draft_words: list[str], ref: dict[str, int], top: int = 12) -> list[tuple[str, int, float]]:
    """Words the draft uses far more than the exemplars (log-odds, add-1 smoothing)."""
    d = Counter(w for w in draft_words if len(w) > 3)
    nd, nr = sum(d.values()), sum(ref.values()) or 1
    scored = []
    for w, k in d.items():
        if k < 3:
            continue
        r = ref.get(w, 0)
        if r < 5:
            continue  # rare in the exemplars = the draft's topic vocabulary, not a style habit
        lo = math.log((k + 1) / (nd + 1)) - math.log((r + 1) / (nr + 1))
        scored.append((w, k, lo))
    return sorted([x for x in scored if x[2] > math.log(4)], key=lambda x: -x[2])[:top]


def fmt(x: float) -> str:
    return f"{x:.2f}" if abs(x) < 1 else f"{x:.1f}"


def cmd_check(a) -> int:
    corpus = json.loads((Path(a.vault) / "logs/style-corpus.json").read_text())
    draft = Path(a.draft)
    secs = draft_sections(draft)
    lines = [f"# Style report — {draft.name}", "",
             f"Generated by `style_bench.py check` on {date.today().isoformat()} against "
             f"{len(corpus['papers'])} exemplars (logs/style-corpus.md, built {corpus['built']}). "
             "Report-only. ⚑ = outside the exemplars' 10–90th percentile: a reason to look, not a verdict.", ""]
    for s in SECTIONS:
        paras = secs[s]
        m = measure([t for _, t in paras])
        if not m:
            lines += [f"## {s}", "", f"_not found or under 150 words in the draft — skipped._", ""]
            continue
        lines += [f"## {s} ({m['words']} words)", "", "| metric | draft | exemplars p25–p50–p75 | |",
                  "|---|---|---|---|"]
        for k, (label, unit) in METRICS.items():
            st = corpus["stats"][s][k]
            if not st:
                continue
            flag = "⚑ high" if m[k] > st["p90"] else "⚑ low" if m[k] < st["p10"] and k not in HIGH_ONLY else ""
            lines.append(f"| {label} {unit} | {fmt(m[k])} | {fmt(st['p25'])}–{fmt(st['p50'])}–{fmt(st['p75'])} | {flag} |")
        ow = overused(words(" ".join(t for _, t in paras)), corpus["vocab"][s])
        if ow:
            lines += ["", "Over-used vs exemplars (count, × exemplar rate): " +
                      ", ".join(f"**{w}** ({k}, ×{math.exp(lo):.0f})" for w, k, lo in ow)]
        hits = [(ln, sent, tell_hits(sent)) for ln, t in paras for sent in sentences(t) if tell_hits(sent)]
        if hits:
            lines += ["", "Sentences with machine-prose tells:", ""]
            lines += [f"- L{ln} [{', '.join(h)}] {sent}" for ln, sent, h in hits]
        lines.append("")
    out = draft.parent / "style-report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {out}")
    return 0


def cmd_passages(a) -> int:
    vault = Path(a.vault)
    corpus = json.loads((vault / "logs/style-corpus.json").read_text())
    papers = [p for p in corpus["papers"] if not a.project or a.project in p["projects"]] or corpus["papers"]
    for p in papers[:a.n]:
        paras = jats_sections(ET.parse(vault / "_library" / f"{p['stem']}.xml").getroot())[a.section]
        print(f"=== [[{p['stem']}]] {p['journal']} {p['year']} ({p['cites_per_year']} cites/yr) — {p['title']}\n")
        print("\n\n".join(paras[:a.paragraphs]) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("corpus")
    c.add_argument("--email", required=True)
    c.add_argument("--min-cites-per-year", type=float, default=15)
    c.add_argument("--exclude-project", action="append", default=[],
                   help="drop papers that belong only to this project (off-field, e.g. a refereed manuscript's refs)")
    k = sub.add_parser("check")
    k.add_argument("draft")
    p = sub.add_parser("passages")
    p.add_argument("--section", choices=SECTIONS, required=True)
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--paragraphs", type=int, default=2)
    p.add_argument("--project", help="prefer exemplars in this project; falls back to all")
    a = ap.parse_args(argv)
    return {"corpus": cmd_corpus, "check": cmd_check, "passages": cmd_passages}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
