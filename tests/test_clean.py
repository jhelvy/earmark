"""The cleaning rules are the product, so this is the bulk of the suite."""

from __future__ import annotations

import pytest

from earmark.clean import CleanOptions, clean, options_for, render


def speech(markdown: str, **kw) -> str:
    opts = kw.pop("opts", None) or CleanOptions(**kw)
    return render(clean(markdown, opts))


CASES = [
    # code
    ("before\n\n```python\nx = 1\n```\n\nafter", "before\n\nafter"),
    ("a\n\n~~~\ncode\n~~~\n\nb", "a\n\nb"),
    # images and links
    ("See ![a chart](chart.png) here.", "See here."),
    ("Read [the paper](https://x.com/y) now.", "Read the paper now."),
    ("Go to <https://example.com> today.", "Go to today."),
    ("Visit https://example.com/page for more.", "Visit for more."),
    # emphasis and inline code
    ("This is **bold** and *italic*.", "This is bold and italic."),
    ("Use `df.head()` first.", "Use df.head() first."),
    ("A ***very*** strong claim.", "A very strong claim."),
    # citations and footnotes
    ("Shown before [12] and after.", "Shown before and after."),
    ("Ranges too [3, 4] work.", "Ranges too work."),
    ("A claim[^1] stands.", "A claim stands."),
    # abbreviations
    ("Many tools, e.g. pandas, exist.", "Many tools, for example pandas, exist."),
    ("Smith et al. found this.", "Smith and others found this."),
    ("See Fig. 3 for detail.", "See Figure 3 for detail."),
    ("Speed vs. accuracy matters.", "Speed versus accuracy matters."),
    # units and numbers
    ("Adoption hit 42% last year.", "Adoption hit 42 percent last year."),
    ("It costs $1.2M per unit.", "It costs 1.2 million dollars per unit."),
    ("About 1,234,567 vehicles.", "About 1234567 vehicles."),
    ("Range 2010–2020 shown.", "Range 2010 to 2020 shown."),
    ("A 60 kWh pack.", "A 60 kilowatt hours pack."),
    # structure
    ("## Methods\n\nWe did things.", "Methods.\n\nWe did things."),
    ("- first item\n- second item", "first item.\n\nsecond item."),
    ("1. one\n2. two", "one.\n\ntwo."),
    ("> quoted text here", "quoted text here"),
    ("a\n\n---\n\nb", "a\n\nb"),
    # frontmatter, html, math
    ("---\ntitle: X\n---\n\nBody text.", "Body text."),
    ("Text <em>with</em> tags.", "Text with tags."),
    ("Before <!-- hidden --> after.", "Before after."),
    ("Let $n$ be large.", "Let n be large."),
    ("Ignore $$\\int_0^1 x\\,dx$$ this.", "Ignore this."),
]


@pytest.mark.parametrize("markdown,expected", CASES)
def test_transforms(markdown, expected):
    assert speech(markdown) == expected


def test_tables_dropped_by_default():
    md = "Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter."
    assert speech(md) == "Before.\n\nAfter."


def test_tables_described_on_request():
    md = "Before.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nAfter."
    assert speech(md, tables="describe") == "Before.\n\nTable omitted.\n\nAfter."


def test_reference_section_is_cut():
    md = "## Body\n\nReal content.\n\n## References\n\nSmith, J. 2020. A paper.\n"
    assert "Smith" not in speech(md)
    assert "Real content." in speech(md)


def test_reference_section_kept_on_request():
    md = "## Body\n\nReal content.\n\n## References\n\nSmith, J. 2020. A paper.\n"
    assert "Smith" in speech(md, drop_references=False)


def test_section_after_references_survives():
    md = "# Paper\n\n## References\n\nSmith 2020.\n\n## Appendix\n\nExtra detail.\n"
    out = speech(md)
    assert "Extra detail." in out
    assert "Smith" not in out


def test_author_year_only_in_paper_profile():
    md = "This was shown (Smith et al., 2020) clearly."
    assert "Smith" in speech(md, opts=options_for("article"))
    assert "Smith" not in speech(md, opts=options_for("paper"))


def test_user_replacements_applied_last():
    md = "The BEV market."
    assert speech(md, replace={"BEV": "battery electric vehicle"}) == (
        "The battery electric vehicle market."
    )


def test_list_items_get_terminal_punctuation():
    blocks = clean("- one\n- two.\n")
    assert [b.text for b in blocks] == ["one.", "two."]
    assert all(b.kind == "item" for b in blocks)


def test_headings_keep_level():
    blocks = clean("# Title\n\n## Sub\n\nbody")
    assert [(b.kind, b.level) for b in blocks[:2]] == [("heading", 1), ("heading", 2)]


def test_abbreviation_expansion_precedes_sentence_ending():
    # The whole reason we expand before splitting: no stray sentence break.
    out = speech("Tools exist, e.g. pandas. Then more text.")
    assert out == "Tools exist, for example pandas. Then more text."


def test_link_inside_heading():
    assert speech("## See [the docs](https://x.com)") == "See the docs."


def test_footnote_definition_block_removed():
    md = "Body text.\n\n[^1]: A footnote body.\n"
    assert speech(md) == "Body text."


def test_table_immediately_after_fence():
    md = "```\ncode\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nEnd."
    assert speech(md) == "End."


def test_unknown_profile_rejected():
    with pytest.raises(ValueError, match="unknown profile"):
        options_for("nope")


def test_figure_dump_dropped():
    md = "Real prose here that is perfectly normal.\n\nehT ehT waL waL lliw lliw reven reven eb eb\n\nMore prose."
    out = speech(md)
    assert "ehT" not in out
    assert "Real prose here" in out and "More prose." in out


def test_prose_with_a_repeat_survives():
    md = "It was very very good and that that clause is fine, honestly it reads normally."
    assert "very very" in speech(md)


def test_emails_removed():
    assert speech("Contact avaswani@google.com for details.") == "Contact for details."


def test_arxiv_stamp_removed():
    md = "Body text.\n\n3202 guA 2 ]LC.sc[ 7v26730.6071:viXra\n\nMore body."
    assert "viXra" not in speech(md)


def test_dangling_conjunction_repaired():
    md = "Models such as [38] and [2] are common."
    assert speech(md, opts=options_for("paper")) == "Models are common."


def test_lead_in_kept_when_it_still_introduces_something():
    md = "Models such as BERT and GPT are common."
    assert "such as BERT and GPT" in speech(md, opts=options_for("paper"))


def test_trailing_lead_in_removed():
    md = "This mirrors earlier work, similar to [30]."
    assert speech(md, opts=options_for("paper")) == "This mirrors earlier work."


def test_html_tag_removal_does_not_fuse_words():
    assert speech("As of 2026<a href='x'>electric</a> vehicles.") == (
        "As of 2026 electric vehicles."
    )


def test_orphan_table_row_dropped():
    md = "Real text.\n\n| A subtopic of sustainability |\n\nMore text."
    out = speech(md)
    assert "subtopic" not in out
    assert "Real text." in out and "More text." in out


def test_adjacent_links_do_not_fuse():
    md = r"As of 2026[\[update\]](https://x.com/e)[electric cars](https://x.com/f) lead."
    assert speech(md) == "As of 2026 electric cars lead."


def test_editorial_markers_removed():
    assert speech("A claim [citation needed] stands.") == "A claim stands."


def test_front_matter_cut_at_abstract():
    md = (
        "Attention Is All You Need\nAshish Vaswani\nGoogle Brain\n"
        "Noam Shazeer\nGoogle Brain\nAbstract\nThe dominant models are based on X.\n"
    )
    out = speech(md, opts=options_for("paper"))
    assert out.startswith("The dominant models")
    assert "Google Brain" not in out


def test_front_matter_kept_by_default_for_articles():
    md = "A Blog Post\nby someone\nAbstract\nBody text here.\n"
    assert "A Blog Post" in speech(md, opts=options_for("article"))


def test_front_matter_anchor_must_appear_early_enough():
    md = "Abstract\nBody.\n"
    # Nothing meaningful precedes the anchor, so nothing is cut.
    assert "Abstract" in speech(md, opts=options_for("paper"))


def test_front_matter_inline_anchor():
    # Some extractors run the whole title page into one line. The anchor has to
    # be far enough in to look like real front matter, so pad it realistically.
    front = (
        "Provided proper attribution is provided, Example Corp hereby grants "
        "permission to reproduce the tables and figures in this paper solely "
        "for use in journalistic or scholarly works. A Very Long Paper Title "
        "Alice Author Example Lab alice@example.com Bob Author Example Lab "
    )
    md = front + "Abstract The real body of the paper starts here.\n"
    out = speech(md, opts=options_for("paper"))
    assert out.startswith("The real body")


def test_inline_anchor_ignored_when_it_appears_immediately():
    md = "Abstract The body starts here right away with no front matter at all.\n"
    assert "Abstract" in speech(md, opts=options_for("paper"))
