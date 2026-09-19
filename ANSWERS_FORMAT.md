# The answers format

A plain-text way to answer someone else's comments on a document you do not own.

Developed on **1001-ob-pcx** and used at scale on **poc-esther** (78 answer files, 300
edit blocks). This file is the written spec; the implementation is
`neuresearch/src/apply_answers.py`.

---

## The one idea

**The answers file is the source of truth. The document is generated from it and is never
hand-edited.**

```
answers_caNN.md   ──apply_answers.py──▶   document_caNN.docx
   (you edit this)                          (never touch this)
```

To change something, edit the answers file and re-run. That is the whole chain of custody:
every edit that reached the document exists as one reviewable block of text, in git, with a
comment id next to it. Nobody has to diff two Word files to find out what was changed or
why.

Two consequences worth stating, because both were learned the hard way:

- **Edits land in colour** (blue by default). The other author's words keep their own
  colour, so at a glance anyone can see which sentences came from us. A silent edit inside
  someone else's prose cannot be reviewed by the person who owns that prose.
- **A comment is resolved only when it is genuinely closed.** A comment still waiting on a
  number nobody has yet **stays**, with no edit attached. Deleting it destroys the record
  of what was asked.

---

## Block grammar

One block per comment. Blocks are separated by a `##` anchor line; fields are `key: value`
and run to the end of the line, except `text:` which may continue over several lines.

```
## id=<comment id>          anchor to a numbered comment in the document
## at=<phrase>              anchor to a phrase instead, when there is no comment

type:     replace | cut | para_after | note | resolve | table_fill | table_new
resolve:  yes              (optional; omit for "no")
find:     <exact text to locate>
text:     <replacement or new text>
widths:   <column widths, table_new only>
```

`find` is matched against the **concatenated** text of the anchored paragraph, so it is
found even when Word has split the phrase across runs or parked a tracked change in the
middle. Surrounding runs keep their own formatting.

---

## The operations

| type | fields | what it does |
|---|---|---|
| `replace` | `find`, `text` | Swaps `find` for `text`, coloured. The workhorse — 239 of 300 blocks. |
| `cut` | — | Deletes the commented text. No fields. |
| `para_after` | `text` | Inserts a coloured paragraph after the commented one, **unlabelled** — document text, not a remark. This is how you *add* information without rewriting what the author already wrote. |
| `note` | `text` | Appends a **labelled** coloured paragraph — a remark to the reviewer, not a text change. **Cannot close a comment.** |
| `resolve` | — | Closes a comment that needed no edit. |
| `table_fill` | `text` | Fills the table the comment sits in. One row per line, cells separated by ` \| `. A cell of `-` keeps what is there. Rows beyond the table's own are cloned from its last row, so a 5-row skeleton takes a 7-row answer. |
| `table_new` | `text`, `widths` | Inserts a bordered table after the commented paragraph — for a caption that never got a table. |

`resolve: yes` deletes the comment and all three of its anchors once the edit has applied.
**A resolve whose edit did not apply is refused** — you cannot close a comment by accident.

---

## Worked examples

A straight rewording that fully answers the comment:

```
## id=3
type: replace
resolve: yes
find: requires substantially larger optical access
text: requires more invasive surgical access to position the imaging optics near the target neurons
```

Answering by addition rather than rewriting:

```
## id=1409
type: replace
resolve: yes
find: defining the minimum viable product and the commercialization route.
text: defining the minimum viable product and the commercialization route. Market size, growth rate, competing platforms and the players serving them are set out under Competition below.
```

Anchoring to a phrase when there is no comment to hang it on:

```
## at=If repeated adjustment proves incompatible with robust MMF imaging
type: cut
```

A comment you cannot close yet — no edit, and it deliberately stays open:

```
## id=274
type: note
text: Needs a real number before submission.
```

---

## Header every answers file

Put the provenance at the top so the next reader knows what generates what:

```markdown
<!-- SOURCE OF TRUTH for <who>'s round-N edits (caNN) on <document>.
     The .docx is GENERATED from this file:
       python ../../../neuresearch/src/apply_answers.py \
         --docx work/<in>.docx --answers answers_caNN.md --out work/<out>.docx
     Every change lands as BLUE text inside <author>'s prose; the reviewer's own
     words keep their colour. `resolve: yes` deletes that comment — used ONLY where
     the edit fully closes it. A comment still waiting on a fact we do not have
     STAYS, with no edit, so the record of what was asked is not destroyed.
     Nothing here invents a number, a name or a result. -->
```

That last sentence is load-bearing. **Nothing in an answers file invents a number, a name
or a result.** If the honest answer is "we do not have this yet", the block is a `note` and
the comment stays open.

---

## Running it

```bash
python neuresearch/src/apply_answers.py \
    --docx  work/document.docx \
    --answers answers_ca01.md \
    --out   work/document_ca01.docx
```

`--color RRGGBB` changes the edit colour (default `0000FF`), `--tag` sets the `note` label.
The input is opened read-only. Python 3.10+, stdlib only.

---

## Why one file per round

`answers_ca01.md`, `answers_ca02.md`, … — one file per review round, never edited after the
round ships. The document at any round is reproducible from its answers file alone, and the
sequence of files is the edit history in readable form. On poc-esther this reached 78 files
without becoming unmanageable, because each one only has to be understood against the
document it was written for.
