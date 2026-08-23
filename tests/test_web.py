import pytest

from earmark.extract.web import _ARXIV_ID, _looks_like_pdf


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://arxiv.org/pdf/1706.03762", "1706.03762"),
        ("https://arxiv.org/abs/2501.00001", "2501.00001"),
        ("https://arxiv.org/pdf/1706.03762v7", "1706.03762"),
        ("http://arxiv.org/abs/cs.CL/0701001", "cs.CL/0701001"),
    ],
)
def test_arxiv_id_parsed(url, expected):
    m = _ARXIV_ID.search(url)
    assert m and m.group("id") == expected


def test_non_arxiv_url_has_no_id():
    assert _ARXIV_ID.search("https://example.com/pdf/1706.03762") is None


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://arxiv.org/pdf/1706.03762", True),
        ("https://example.com/paper.pdf", True),
        ("https://example.com/article", False),
    ],
)
def test_pdf_detection(url, expected):
    assert _looks_like_pdf(url) is expected


def test_arxiv_abs_url_routes_to_the_pdf():
    """/abs/ is the link arXiv shows, so it is the one people paste; extracting
    the landing page narrates "View PDF" and the arXivLabs footer."""
    from earmark.extract.web import arxiv_pdf_url

    assert arxiv_pdf_url("https://arxiv.org/abs/1706.03762") == (
        "https://arxiv.org/pdf/1706.03762"
    )
    assert arxiv_pdf_url("http://arxiv.org/abs/cs.CL/0701001") == (
        "https://arxiv.org/pdf/cs.CL/0701001"
    )


def test_arxiv_pdf_and_other_urls_are_left_alone():
    from earmark.extract.web import arxiv_pdf_url

    assert arxiv_pdf_url("https://arxiv.org/pdf/1706.03762") is None
    assert arxiv_pdf_url("https://example.com/abs/thing") is None
