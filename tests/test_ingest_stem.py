"""The stem-collision rule ingest.py uses: an existing file is the same paper
only if the new paper's title words appear on its first page."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ingest import title_in_text  # noqa: E402

NEW = "Olfactory projections to the hypothalamus"


def test_other_paper_holding_the_stem_is_not_a_match():
    held = ("Neurobiology of Aging 1991. The Distribution of Tangles, Plaques and "
            "Related Immunohistochemical Markers in Healthy Aging and Alzheimer's Disease")
    assert not title_in_text(NEW, held)


def test_same_paper_is_a_match():
    held = "THE JOURNAL OF COMPARATIVE NEUROLOGY 306 (1991) Olfactory Projections to the Hypothalamus"
    assert title_in_text(NEW, held)
