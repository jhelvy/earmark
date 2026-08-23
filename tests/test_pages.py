"""Page furniture: footnotes, page numbers, running heads, stamps."""

from __future__ import annotations

import pytest

from earmark.extract.pages import (
    is_page_number,
    is_stamp,
    running_heads,
    strip_furniture,
)


def body(n: int, prefix: str = "Body line") -> list[str]:
    return [f"{prefix} {i} carrying real sentences of argument." for i in range(n)]


def page(*parts: str) -> str:
    return "\n".join(parts)


@pytest.mark.parametrize(
    "line,expected",
    [
        ("4", True),
        ("  12  ", True),
        ("- 7 -", True),
        ("[3]", True),
        ("xiv", True),
        ("", False),
        ("   ", False),
        ("-", False),
        ("civil", False),
        ("Page 4", False),
        ("4 Why Self-Attention", False),
        ("12345", False),
    ],
)
def test_is_page_number(line, expected):
    assert is_page_number(line) is expected


@pytest.mark.parametrize(
    "line",
    [
        "arXiv:1706.03762v7  [cs.CL]  2 Aug 2023",
        "31st Conference on Neural Information Processing Systems, Long Beach",
        "Proceedings of the 2020 Workshop",
        "Preprint. Under review.",
        "© 2017 Association for Computing Machinery",
    ],
)
def test_is_stamp(line):
    assert is_stamp(line)


def test_stamp_does_not_match_body():
    assert not is_stamp("Conference attendance rose in 2019.")


def test_symbol_footnote_block_removed():
    """The bug this module exists for: an author-contribution note read aloud
    immediately after the abstract."""
    p = page(
        *body(20),
        "large and limited training data.",
        "∗Equal contribution. Listing order is random. Jakob proposed replacing",
        "RNNs with self-attention and started the effort to evaluate this idea.",
        "†Work performed while at Google Brain.",
        "31st Conference on Neural Information Processing Systems, Long Beach.",
        "arXiv:1706.03762v7  [cs.CL]  2 Aug 2023",
    )
    out = strip_furniture([p])[0]
    assert out.endswith("large and limited training data.")
    assert "Equal contribution" not in out
    assert "arXiv" not in out


def test_numbered_footnote_and_page_number_removed():
    p = page(
        *body(20),
        "queries, keys and values we then perform the attention function,",
        "4To illustrate why the dot products get large, assume that q and k",
        "are independent random variables with mean 0 and variance 1.",
        "4",
    )
    out = strip_furniture([p])[0]
    assert "To illustrate" not in out
    assert out.endswith("attention function,")


def test_inline_superscript_removed_only_for_cut_footnotes():
    p = page(
        *body(18),
        "pushing the softmax into regions where it has small gradients 4.",
        "We also report results in Table 4. See also Figure 4.",
        "4To illustrate why the dot products get large, assume independence.",
        "4",
    )
    out = strip_furniture([p])[0]
    assert "small gradients." in out
    assert "in Table 4." in out
    assert "Figure 4." in out


def test_inline_number_untouched_without_a_footnote():
    p = page(*body(18), "Accuracy improved by 4. That was unexpected.")
    out = strip_furniture([p])[0]
    assert "improved by 4." in out


def test_bullet_at_page_bottom_survives():
    """A bullet is "* item"; a footnote is "*Equal". The space is the whole
    difference, and getting it wrong would delete a real list."""
    p = page(*body(15), "The model has three parts:", "* an encoder", "* a decoder")
    out = strip_furniture([p])[0]
    assert "an encoder" in out
    assert "a decoder" in out


def test_numbered_heading_at_page_bottom_survives():
    p = page(*body(15), "4 Why Self-Attention", "In this section we compare.")
    out = strip_furniture([p])[0]
    assert "4 Why Self-Attention" in out


def test_footnote_high_on_the_page_is_left_alone():
    """Above the tail window a marker is far likelier to be real text than a
    footnote, and cutting there would take the rest of the page with it."""
    p = page("∗ this looks like a marker", *body(30))
    out = strip_furniture([p])[0]
    assert "Body line 29" in out


def test_oversized_note_block_is_left_alone():
    p = page(*body(10), "1Footnote", *body(40, "More note"))
    out = strip_furniture([p])[0]
    assert "More note 39" in out


def test_running_heads_removed():
    """Body text differs page to page, as real prose does; only the banner is
    verbatim-identical, and that repetition is the entire signal."""
    pages = [
        page("J. Helveston et al. / Energy Policy 142", *body(8, f"Page {i} line"), str(i))
        for i in range(1, 6)
    ]
    out = strip_furniture(pages)
    assert not any("Energy Policy" in p for p in out)
    assert all(f"Page {i} line 0" in p for i, p in enumerate(out, 1))


def test_running_head_needs_several_pages():
    pages = [page("Repeated banner", *body(8)), page("Repeated banner", *body(8))]
    assert running_heads(pages) == set()


def test_repeated_body_line_is_not_a_running_head():
    """Only the outermost two lines of a page are eligible, so a sentence that
    happens to recur mid-page stays."""
    pages = [page(*body(4), "A recurring refrain.", *body(4)) for _ in range(5)]
    out = strip_furniture(pages)
    assert all("A recurring refrain." in p for p in out)


def test_empty_pages_dropped():
    assert strip_furniture(["", "  \n \n", page(*body(5))]) == [
        strip_furniture([page(*body(5))])[0]
    ]


def test_short_page_is_not_mangled():
    assert strip_furniture(["One line only."]) == ["One line only."]
