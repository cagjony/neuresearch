#!/usr/bin/env python3
"""Check every `"quote" [citekey]` pair in a Markdown digest against _library/<citekey>.xml (itertext, whitespace collapsed).
    python src/quote_check.py <digest.md> [extra text]    (run from the vault root; extra text: e.g. a planted fake to test)
"""
md = open(sys.argv[1]).read() + (sys.argv[2] if len(sys.argv) > 2 else "")
norm = lambda s: re.sub(r"\s+", " ", s).strip()
src = {}
ok = bad = 0
for q, k in re.findall(r'"([^"]{8,})" \[([a-z0-9]+)\]', md):
    if k not in src:
        src[k] = norm(" ".join(ET.parse(f"_library/{k}.xml").getroot().itertext()))
    parts = [norm(p) for p in q.split(" … ")]
    if all(p in src[k] for p in parts): ok += 1
    else: bad += 1; print("NOT FOUND", k, "|", q[:120])
print(f"{ok}/{ok+bad} quotes found verbatim, {bad} failed ({len(src)} citekeys)")
