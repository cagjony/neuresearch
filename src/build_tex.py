#!/usr/bin/env python3
import os
import re
import argparse
from pathlib import Path

preamble = r"""
\documentclass[a4paper,fleqn]{cas-sc}

\usepackage[numbers,sort&compress]{natbib}
\usepackage{graphicx}
\usepackage[labelformat=empty,labelsep=none]{caption}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[utf8]{inputenc}

\begin{document}
% Our captions carry their own "Figure N." label, matching the bold **Figure N**
% references in the text. cas-common.sty hardcodes its caption as
% \textbf{\color{scolor}#1:}~#2 inside \__make_fig_caption:nn and never consults
% the caption package, so labelformat=empty/labelsep=none left a bare ": " at the
% head of every caption. Overriding that one function is what actually removes it;
% #1 (the label) is dropped and only #2 (our caption text) is set.
\ExplSyntaxOn
\cs_set:Npn \__make_fig_caption:nn #1#2
  {
    \l_fig_align_tl
    \skip_vertical:N \l_fig_abovecap_skip
    \parbox { \l_fig_width_dim }
      { \unskip \ignorespaces \sffamily \small #2 \par }
  }
\ExplSyntaxOff
\let\WriteBookmarks\relax
\def\floatpagepagefraction{.75}
\shorttitle{Olfactory testing in Alzheimer's disease: from report to odour-evoked response}
\shortauthors{E. Ayan et~al.}

\title [mode = title]{Olfactory testing in Alzheimer's disease: from report to odour-evoked response}                      

\author[1,2]{Esra Ayan}[orcid=0000-0001-7906-4426]
\fnmark[1]
\credit{Investigation, Writing - Original Draft, Writing - Review \& Editing, Visualization}

\author[2]{B\"u\c{s}ra Z\"uleyha Do\u{g}an}[orcid=0009-0002-1174-2379]
\fnmark[1]
\credit{Investigation, Writing - Original Draft, Writing - Review \& Editing}

\author[2]{Meryem Sinem Uyar}[orcid=0009-0002-0963-0247]
\fnmark[1]
\credit{Investigation, Writing - Original Draft, Writing - Review \& Editing}

\author[2]{Beyza Sevgili}[orcid=0009-0001-0586-230X]

\author[2]{M. \.Ikbal Alp}[orcid=0000-0003-2075-7724]
\cormark[1]
\ead{malp@medipol.edu.tr}
\credit{Writing - Review \& Editing, Supervision, Project administration, Funding acquisition}

\author[2,3,4]{{\c{C}}a\u{g}atay Ayd{\i}n}[orcid=0000-0002-7216-1079]
\cormark[2]
\ead{cagatay.aydin1@medipol.edu.tr} 
\credit{Investigation, Writing - Original Draft, Writing - Review \& Editing, Visualization, Supervision, Project administration}

\affiliation[1]{organization={Experimental Medicine Research and Application Center, University of Health Sciences}, city={Istanbul}, country={T\"urkiye}}
\affiliation[2]{organization={Research Institute for Health Sciences and Technologies (SABITA), Neuroscience Research Center, Istanbul Medipol University}, city={Istanbul}, country={T\"urkiye}}
\affiliation[3]{organization={Electrical and Electronics Engineering Department, Istanbul Medipol University}, city={Istanbul}, country={T\"urkiye}}
\affiliation[4]{organization={VIB-KU Leuven Center for Neuroscience, Neurophysiology Technology Unit}, city={Leuven}, country={Belgium}}

\cortext[cor1]{Corresponding author}
\cortext[cor2]{Corresponding author}
\fntext[fn1]{These authors contributed equally to this work.}

\begin{abstract}
Olfactory dysfunction is the earliest and most robust sensory sign of Alzheimer's disease (AD), and a smell test is among the least invasive assessments in medicine, yet decades of preclinical evidence (Phase 1) have not produced a standardized clinical assay (Phase 2). Qualifying one requires a measure of the olfactory system's capacity. Clinical olfactometry already acquires that measure: the threshold subtest of the standard battery runs a forced-choice staircase over a graded dilution series. The series is then collapsed to a single threshold and summed with discrimination and identification into one composite score, so the function it describes never reaches the literature, and a fall in the total cannot be attributed to the periphery or to cognition. Rodent olfaction research made the opposite choice, varying difficulty deliberately and reporting performance at each level, together with the time taken to decide. The two literatures are thus incomplete in opposite directions: the clinic samples densely and reports a point, the laboratory samples coarsely and reports a function, and neither fits the curve that both are close to. We coded all 93 studies cited here on what each one measured, and found the two literatures share no behavioural construct. We propose that olfactory capacity be reported in patients as the curve it already is, with its threshold, its slope and the time taken, and that odour-evoked recording be used to localise where a change in that curve arose.
\end{abstract}

\begin{keywords}
Alzheimer's disease \sep Olfaction \sep Biomarkers \sep Olfactory event-related potentials \sep Translational neuroscience
\end{keywords}

\maketitle

"""

# The H1 title block pandoc emits. Pandoc hard-wraps inside \section{...},
# so the title spans several lines and the brace group must be matched with
# DOTALL rather than a line-bounded pattern.
_TITLE_SECTION = re.compile(
    r"\\hypertarget\{[^}]*\}\{%\s*\n\\section\{.*?\}\\label\{[^}]*\}\}",
    re.S)

# Applied in ONE pass. Doing these as sequential str.replace calls collapses
# every level onto \section, because the subsubsection->subsection rewrite
# feeds its own output into the subsection->section rewrite.
_LIFT = {"subsubsection": "subsection", "subsection": "section"}
_LIFT_RE = re.compile(r"\\(subsubsection|subsection)\{")


def _lift_headings(body: str) -> str:
    """Remove the duplicated title section and lift every heading one level."""
    body, hits = _TITLE_SECTION.subn("", body, count=1)
    if not hits:
        # Nothing to lift is a legitimate state (a body with no H1); say so
        # rather than silently reshaping headings that were already correct.
        print("build_tex: no H1 title section found; heading levels left as-is")
        return body
    return _LIFT_RE.sub(lambda m: "\\" + _LIFT[m.group(1)] + "{", body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True, type=Path)
    args = parser.parse_args()

    body_path = args.project_dir / "submission" / "body.tex"
    out_path = args.project_dir / "submission" / "manuscript.tex"

    with open(body_path, "r", encoding="utf-8") as f:
        body = f.read()

    # Make images fit to page width
    body = body.replace(r"\includegraphics{", r"\includegraphics[width=0.8\linewidth]{")

    # The markdown H1 is the paper title, which the preamble already sets via
    # \title. Pandoc renders it as \section, so without this the title appears
    # twice - once stale on the running head, once as numbered section 1 - and
    # every real heading sinks a level, producing "1.5.2." on a review paper.
    # Drop that section and promote everything under it.
    body = _lift_headings(body)

    # Handle unicode characters for pdflatex
    body = body.replace("β", "$\\beta$")
    body = body.replace("α", "$\\alpha$")
    body = body.replace("ε", "$\\epsilon$")

    footer = r"""
\bibliographystyle{cas-model2-names}
\bibliography{references}
\end{document}
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(preamble + body + footer)

    print(f"Generated {out_path}")

if __name__ == "__main__":
    main()
