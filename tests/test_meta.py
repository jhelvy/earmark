from earmark.extract.meta import Metadata, resolve_meta


def test_flag_beats_everything():
    meta = resolve_meta("# Heading", "/tmp/file.pdf",
                        extracted=Metadata(title="Extracted"), title="Explicit")
    assert meta.title == "Explicit"


def test_extracted_beats_heading():
    meta = resolve_meta("# Heading", "/tmp/file.pdf", extracted=Metadata(title="Extracted"))
    assert meta.title == "Extracted"


def test_heading_beats_filename():
    meta = resolve_meta("# Heading", "/tmp/some_file.pdf")
    assert meta.title == "Heading"


def test_filename_is_the_last_resort():
    meta = resolve_meta("no heading here", "/tmp/some_file.pdf")
    assert meta.title == "some file"


def test_implausible_author_rejected():
    junk = "Authority control databases National United States France BnF data Czech Republic"
    meta = resolve_meta("body", "https://x.com/a", extracted=Metadata(author=junk))
    assert meta.author is None


def test_real_byline_kept():
    meta = resolve_meta("body", "https://x.com/a", extracted=Metadata(author="Ashish Vaswani"))
    assert meta.author == "Ashish Vaswani"
