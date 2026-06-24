"""Tests for F102: PDF text extraction utility using PyMuPDF."""

import pathlib
import tempfile

import fitz  # PyMuPDF
import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


# ============================================================
# Helpers: create test PDF fixtures
# ============================================================


def _create_simple_pdf(path: pathlib.Path, text: str = "Hello, Bob!") -> None:
    """Create a simple single-page PDF with the given text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _create_multipage_pdf(path: pathlib.Path, pages: list[str]) -> None:
    """Create a multi-page PDF with one text block per page."""
    doc = fitz.open()
    for page_text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), page_text)
    doc.save(str(path))
    doc.close()


def _create_password_protected_pdf(path: pathlib.Path, text: str = "Secret") -> None:
    """Create a password-protected PDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret123")
    doc.close()


def _create_corrupted_file(path: pathlib.Path) -> None:
    """Create a file that looks like a PDF header but is corrupted."""
    path.write_bytes(b"%PDF-1.4 corrupted garbage data here\x00\xff\xfe")


# ============================================================
# Step 1: pdf_utils.py exists and uses 'import fitz'
# ============================================================


class TestPdfUtilsFileExists:
    """Step 1: Create pdf_utils.py with 'import fitz'."""

    def test_pdf_utils_file_exists(self):
        path = WORKSPACE / "src" / "bob" / "pdf_utils.py"
        assert path.exists(), "src/bob/pdf_utils.py must exist"

    def test_pdf_utils_importable(self):
        import bob.pdf_utils  # noqa: F401

    def test_pdf_utils_imports_fitz(self):
        import bob.pdf_utils
        import inspect

        source = inspect.getsource(bob.pdf_utils)
        assert "import fitz" in source, "pdf_utils.py must contain 'import fitz'"


# ============================================================
# Step 2: PDFContent dataclass
# ============================================================


class TestPDFContent:
    """Step 2: Implement PDFContent dataclass with text, pages, metadata."""

    def test_pdfcontent_importable(self):
        from bob.pdf_utils import PDFContent

        assert PDFContent is not None

    def test_pdfcontent_has_text_field(self):
        from bob.pdf_utils import PDFContent

        content = PDFContent(text="hello", pages=["hello"], metadata={})
        assert content.text == "hello"

    def test_pdfcontent_has_pages_field(self):
        from bob.pdf_utils import PDFContent

        content = PDFContent(text="a\nb", pages=["a", "b"], metadata={})
        assert content.pages == ["a", "b"]
        assert len(content.pages) == 2

    def test_pdfcontent_has_metadata_field(self):
        from bob.pdf_utils import PDFContent

        meta = {"author": "Bob", "page_count": 3}
        content = PDFContent(text="", pages=[], metadata=meta)
        assert content.metadata["author"] == "Bob"
        assert content.metadata["page_count"] == 3

    def test_pdfcontent_is_dataclass(self):
        import dataclasses

        from bob.pdf_utils import PDFContent

        assert dataclasses.is_dataclass(PDFContent)


# ============================================================
# Step 3: validate_pdf()
# ============================================================


class TestValidatePdf:
    """Step 3: Implement validate_pdf() to check for corrupted/password-protected PDFs."""

    def test_validate_pdf_importable(self):
        from bob.pdf_utils import validate_pdf

        assert callable(validate_pdf)

    def test_valid_pdf_returns_true(self, tmp_path):
        pdf_path = tmp_path / "valid.pdf"
        _create_simple_pdf(pdf_path)
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(pdf_path) is True

    def test_nonexistent_file_returns_false(self, tmp_path):
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(tmp_path / "missing.pdf") is False

    def test_corrupted_pdf_returns_false(self, tmp_path):
        corrupted = tmp_path / "corrupted.pdf"
        _create_corrupted_file(corrupted)
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(corrupted) is False

    def test_password_protected_pdf_returns_false(self, tmp_path):
        locked = tmp_path / "locked.pdf"
        _create_password_protected_pdf(locked)
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(locked) is False

    def test_non_pdf_file_returns_false(self, tmp_path):
        txt = tmp_path / "readme.txt"
        txt.write_text("just plain text")
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(txt) is False

    def test_validate_pdf_accepts_str_path(self, tmp_path):
        pdf_path = tmp_path / "str_path.pdf"
        _create_simple_pdf(pdf_path)
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(str(pdf_path)) is True

    def test_multipage_pdf_is_valid(self, tmp_path):
        pdf_path = tmp_path / "multi.pdf"
        _create_multipage_pdf(pdf_path, ["Page 1", "Page 2", "Page 3"])
        from bob.pdf_utils import validate_pdf

        assert validate_pdf(pdf_path) is True


# ============================================================
# Step 4: extract_pdf_text()
# ============================================================


class TestExtractPdfText:
    """Step 4: Implement extract_pdf_text() with error handling."""

    def test_extract_pdf_text_importable(self):
        from bob.pdf_utils import extract_pdf_text

        assert callable(extract_pdf_text)

    def test_extract_returns_pdfcontent(self, tmp_path):
        from bob.pdf_utils import PDFContent, extract_pdf_text

        pdf_path = tmp_path / "sample.pdf"
        _create_simple_pdf(pdf_path, "Sample text here")
        result = extract_pdf_text(pdf_path)
        assert isinstance(result, PDFContent)

    def test_extract_text_content(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        pdf_path = tmp_path / "content.pdf"
        _create_simple_pdf(pdf_path, "Extract me please")
        result = extract_pdf_text(pdf_path)
        assert "Extract me please" in result.text

    def test_extract_multipage_text(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        pdf_path = tmp_path / "multi.pdf"
        _create_multipage_pdf(pdf_path, ["Page one text", "Page two text", "Page three text"])
        result = extract_pdf_text(pdf_path)
        assert "Page one text" in result.text
        assert "Page two text" in result.text
        assert "Page three text" in result.text

    def test_extract_pages_list(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        pdf_path = tmp_path / "pages.pdf"
        _create_multipage_pdf(pdf_path, ["Alpha", "Beta", "Gamma"])
        result = extract_pdf_text(pdf_path)
        assert len(result.pages) == 3
        assert "Alpha" in result.pages[0]
        assert "Beta" in result.pages[1]
        assert "Gamma" in result.pages[2]

    def test_extract_metadata_has_page_count(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        pdf_path = tmp_path / "meta.pdf"
        _create_multipage_pdf(pdf_path, ["A", "B"])
        result = extract_pdf_text(pdf_path)
        assert "page_count" in result.metadata
        assert result.metadata["page_count"] == 2

    def test_extract_nonexistent_raises(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        with pytest.raises(FileNotFoundError):
            extract_pdf_text(tmp_path / "nope.pdf")

    def test_extract_corrupted_raises(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        corrupted = tmp_path / "bad.pdf"
        _create_corrupted_file(corrupted)
        with pytest.raises(ValueError, match="(?i)corrupt|invalid|cannot|failed"):
            extract_pdf_text(corrupted)

    def test_extract_password_protected_raises(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        locked = tmp_path / "locked.pdf"
        _create_password_protected_pdf(locked)
        with pytest.raises(ValueError, match="(?i)password|protected|encrypted"):
            extract_pdf_text(locked)

    def test_extract_accepts_str_path(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        pdf_path = tmp_path / "strpath.pdf"
        _create_simple_pdf(pdf_path, "string path test")
        result = extract_pdf_text(str(pdf_path))
        assert "string path test" in result.text


# ============================================================
# Step 5: chunk_pdf_for_context()
# ============================================================


class TestChunkPdfForContext:
    """Step 5: Implement chunk_pdf_for_context() for token limits."""

    def test_chunk_importable(self):
        from bob.pdf_utils import chunk_pdf_for_context

        assert callable(chunk_pdf_for_context)

    def test_chunk_returns_list_of_strings(self, tmp_path):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        content = PDFContent(text="short text", pages=["short text"], metadata={})
        chunks = chunk_pdf_for_context(content, chunk_size=1000)
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)

    def test_short_text_single_chunk(self):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        content = PDFContent(text="Hello world", pages=["Hello world"], metadata={})
        chunks = chunk_pdf_for_context(content, chunk_size=1000)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]

    def test_long_text_multiple_chunks(self):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        long_text = "word " * 500  # ~2500 chars
        content = PDFContent(text=long_text, pages=[long_text], metadata={})
        chunks = chunk_pdf_for_context(content, chunk_size=100)
        assert len(chunks) > 1

    def test_chunks_do_not_exceed_size(self):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        long_text = "word " * 500
        content = PDFContent(text=long_text, pages=[long_text], metadata={})
        chunks = chunk_pdf_for_context(content, chunk_size=200)
        for chunk in chunks:
            assert len(chunk) <= 200

    def test_chunks_cover_full_text(self):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        text = "The quick brown fox jumps over the lazy dog. " * 20
        content = PDFContent(text=text, pages=[text], metadata={})
        chunks = chunk_pdf_for_context(content, chunk_size=100)
        reassembled = "".join(chunks)
        # All words from original should appear in reassembled text
        for word in ["quick", "brown", "fox", "lazy", "dog"]:
            assert word in reassembled

    def test_empty_text_returns_empty_list(self):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        content = PDFContent(text="", pages=[], metadata={})
        chunks = chunk_pdf_for_context(content, chunk_size=100)
        assert chunks == []

    def test_default_chunk_size(self):
        from bob.pdf_utils import PDFContent, chunk_pdf_for_context

        content = PDFContent(text="test", pages=["test"], metadata={})
        # Should work without explicit chunk_size (has a default)
        chunks = chunk_pdf_for_context(content)
        assert len(chunks) >= 1


# ============================================================
# Step 6 & 7: Integration tests with clear error messages
# ============================================================


class TestIntegrationAndErrorMessages:
    """Steps 6-7: Test with various PDF types and verify error messages."""

    def test_full_roundtrip_valid_pdf(self, tmp_path):
        from bob.pdf_utils import (
            chunk_pdf_for_context,
            extract_pdf_text,
            validate_pdf,
        )

        pdf_path = tmp_path / "roundtrip.pdf"
        _create_simple_pdf(pdf_path, "Full roundtrip test content")

        assert validate_pdf(pdf_path) is True
        content = extract_pdf_text(pdf_path)
        assert "Full roundtrip test content" in content.text
        chunks = chunk_pdf_for_context(content, chunk_size=5000)
        assert len(chunks) >= 1

    def test_corrupted_pdf_error_is_descriptive(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        corrupted = tmp_path / "bad.pdf"
        _create_corrupted_file(corrupted)
        with pytest.raises(ValueError) as exc_info:
            extract_pdf_text(corrupted)
        msg = str(exc_info.value).lower()
        # Error message must be useful to the human
        assert any(w in msg for w in ["corrupt", "invalid", "cannot", "failed", "not a valid"])

    def test_password_protected_error_is_descriptive(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        locked = tmp_path / "locked.pdf"
        _create_password_protected_pdf(locked)
        with pytest.raises(ValueError) as exc_info:
            extract_pdf_text(locked)
        msg = str(exc_info.value).lower()
        assert any(w in msg for w in ["password", "protected", "encrypted"])

    def test_nonexistent_error_is_descriptive(self, tmp_path):
        from bob.pdf_utils import extract_pdf_text

        with pytest.raises(FileNotFoundError) as exc_info:
            extract_pdf_text(tmp_path / "nonexistent.pdf")
        msg = str(exc_info.value).lower()
        assert "not found" in msg or "no such" in msg or "does not exist" in msg

    def test_multipage_pdf_full_workflow(self, tmp_path):
        from bob.pdf_utils import (
            chunk_pdf_for_context,
            extract_pdf_text,
            validate_pdf,
        )

        pdf_path = tmp_path / "multipage.pdf"
        pages = [f"Content for page {i+1}" for i in range(5)]
        _create_multipage_pdf(pdf_path, pages)

        assert validate_pdf(pdf_path) is True
        content = extract_pdf_text(pdf_path)
        assert content.metadata["page_count"] == 5
        assert len(content.pages) == 5
        for i, page_text in enumerate(content.pages):
            assert f"Content for page {i+1}" in page_text

        chunks = chunk_pdf_for_context(content, chunk_size=50)
        assert len(chunks) > 1
