#!/usr/bin/env python3
import os
import argparse
from pathlib import Path

preamble = r"""
\documentclass[a4paper,fleqn]{cas-sc}

\usepackage[numbers]{natbib}
\usepackage{graphicx}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[utf8]{inputenc}

\begin{document}
\let\WriteBookmarks\relax
\def\floatpagepagefraction{1}
\def\textpagefraction{.001}
\shorttitle{Olfactory testing in Alzheimer's disease: a Phase 2 problem}
\shortauthors{E. Ayan et~al.}

\title [mode = title]{Olfactory testing in Alzheimer's disease: a Phase 2 problem}                      

\author[1,2]{Esra Ayan}[orcid=0000-0001-7906-4426]
\credit{Placeholder role}

\author[2]{B\"u\c{s}ra Z\"uleyha Do\u{g}an}[orcid=0000-0000-0000-0000]
\credit{Placeholder role}

\author[2]{Meryem Sinem Uyar}[orcid=0000-0000-0000-0000]
\credit{Placeholder role}

\author[2]{Beyza Sevgili}[orcid=0000-0000-0000-0000]
\credit{Placeholder role}

\author[2]{M. \.Ikbal Alp}[orcid=0000-0003-2075-7724]
\cormark[1]
\ead{malp@medipol.edu.tr}
\credit{Placeholder role}

\author[2,3,4]{{\c{C}}a\u{g}atay Ayd{\i}n}[orcid=0000-0002-7216-1079]
\cormark[2]
\ead{cagatay.aydin1@medipol.edu.tr} 
\credit{Placeholder role}

\affiliation[1]{organization={Experimental Medicine Research and Application Center, University of Health Sciences}, city={Istanbul}, country={T\"urkiye}}
\affiliation[2]{organization={Research Institute for Health Sciences and Technologies (SABITA), Neuroscience Research Center, Istanbul Medipol University}, city={Istanbul}, country={T\"urkiye}}
\affiliation[3]{organization={Electrical and Electronics Engineering Department, Istanbul Medipol University}, city={Istanbul}, country={T\"urkiye}}
\affiliation[4]{organization={VIB-KU Leuven Center for Neuroscience, Neurophysiology Technology Unit}, city={Leuven}, country={Belgium}}

\cortext[cor1]{Corresponding author}
\cortext[cor2]{Corresponding author}

\begin{abstract}
Sensory impairments are increasingly recognized as early, non-cognitive manifestations of Alzheimer's disease (AD). Among these, olfactory dysfunction is the most robust and appears earliest. However, despite decades of compelling preclinical evidence (Phase 1), olfactory testing has not transitioned into clinical practice (Phase 2). This review argues that the bottleneck is a fundamental construct mismatch between animal models and clinical diagnostics. While mouse paradigms evaluate basic odor detection and discrimination, human tests predominantly measure high-level semantic odor identification. We propose a strategic alignment of olfactory constructs across species to overcome this translational barrier.
\end{abstract}

\begin{keywords}
Alzheimer's disease \sep Olfaction \sep Biomarkers
\end{keywords}

\maketitle

"""

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
