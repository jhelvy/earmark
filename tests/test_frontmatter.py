"""Front matter: the note that stops convert from re-cleaning your edits."""

from __future__ import annotations

from earmark import frontmatter
from earmark.extract.meta import Metadata


def test_round_trip():
    meta = Metadata(title="A Paper", author="Jane Doe", date="2026-01-01",
                    source="https://example.com/a")
    parsed = frontmatter.parse(frontmatter.dump(meta, "Body text."))
    assert parsed.fields["title"] == "A Paper"
    assert parsed.fields["author"] == "Jane Doe"
    assert parsed.body == "Body text."
    assert parsed.is_cleaned


def test_a_title_may_contain_a_colon():
    meta = Metadata(title="Attention: All You Need")
    parsed = frontmatter.parse(frontmatter.dump(meta, "Body."))
    assert parsed.fields["title"] == "Attention: All You Need"


def test_empty_fields_are_left_out():
    text = frontmatter.dump(Metadata(title="A"), "Body.")
    assert "author:" not in text and "date:" not in text


def test_no_front_matter_means_all_body():
    parsed = frontmatter.parse("# A Heading\n\nBody.")
    assert parsed.fields == {} and parsed.body.startswith("# A Heading")
    assert not parsed.is_cleaned


def test_an_unterminated_block_is_not_front_matter():
    """A document that merely opens with a rule must not lose its first half."""
    text = "---\ntitle: A\n\nBody that never closed the block."
    parsed = frontmatter.parse(text)
    assert parsed.fields == {} and parsed.body == text


def test_someone_elses_front_matter_is_not_cleaned():
    parsed = frontmatter.parse("---\ntitle: A Post\nlayout: post\n---\n\nBody.")
    assert parsed.fields["title"] == "A Post"
    assert not parsed.is_cleaned


def test_cleaned_can_be_withheld():
    text = frontmatter.dump(Metadata(title="A"), "Body.", cleaned=False)
    assert not frontmatter.parse(text).is_cleaned


def test_the_cleaner_never_speaks_front_matter():
    from earmark.clean import clean, options_for, render

    text = frontmatter.dump(Metadata(title="A Paper", author="Jane"), "The body.")
    spoken = render(clean(text, options_for("article")))
    assert "earmark: cleaned" not in spoken
    assert "The body." in spoken
