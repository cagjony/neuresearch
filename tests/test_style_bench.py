import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import style_bench as sb

FILLER = " ".join(["The cells responded to the drug in every slice we tested."] * 20)


def test_sentences_keep_abbreviations_and_decimals():
    s = sb.sentences("Smith et al. found 0.5 Hz rhythms (Fig. 2). We did not. Why?")
    assert s == ["Smith et al. found 0.5 Hz rhythms (Fig. 2).", "We did not.", "Why?"]


def test_numeric_ranges_are_not_dashes():
    assert sb.measure([FILLER + " at 50–100 µM, 0.3–3.8"])["dash_rate"] == 0
    assert sb.measure([FILLER + " a cell — or two"])["dash_rate"] > 0


def test_markdown_percent_does_not_truncate(tmp_path):
    md = tmp_path / "m.md"
    md.write_text(f"# Results\n\nAbout 80% of the rise stayed. {FILLER}\n\n# Methods\n\nignored text here and more words.\n")
    paras = sb.draft_sections(md)["results"]
    assert len(paras) == 1 and paras[0][1].endswith("we tested.")
    assert sb.draft_sections(md)["intro"] == []


def test_jats_untitled_intro_and_captions_skipped():
    root = ET.fromstring(
        "<article><body><p>Untitled opening paragraph that sets up the question here.</p>"
        "<sec><title>Results</title><p>Main result text that the reader should see now.</p>"
        "<fig><caption><p>Caption text that is not running prose at all.</p></caption></fig></sec>"
        "</body></article>")
    secs = sb.jats_sections(root)
    assert secs["intro"] == ["Untitled opening paragraph that sets up the question here."]
    assert secs["results"] == ["Main result text that the reader should see now."]


def test_overused_ignores_topic_words():
    draft = ["carbenoxolone"] * 10 + ["crucial"] * 10 + ["the"] * 100
    words = [w for w, _, _ in sb.overused(draft, {"crucial": 5, "the": 100000})]
    assert words == ["crucial"]


def test_subsection_named_background_stays_in_methods(tmp_path):
    tex = tmp_path / "m.tex"
    tex.write_text(f"\\section{{Introduction}}\n\nIntro text. {FILLER}\n\n\\section{{Methods}}\n"
                   f"\\subsection*{{Background}}\n\nMethods text that must not count. {FILLER}\n\n"
                   f"\\section{{Results}}\n\\subsection*{{First result}}\n\nResult text. {FILLER}\n")
    secs = sb.draft_sections(tex)
    assert len(secs["intro"]) == 1 and len(secs["results"]) == 1


def test_markdown_title_then_level2_sections(tmp_path):
    md = tmp_path / "m.md"
    md.write_text(f"# Paper title\n\n## Introduction\n\nIntro text here. {FILLER}\n\n## Methods\n\n"
                  f"Methods words. {FILLER}\n")
    secs = sb.draft_sections(md)
    assert len(secs["intro"]) == 1 and secs["intro"][0][1].startswith("Intro")
