"""PDF text extraction utility using PyMuPDF.

Provides functions to validate, extract text from, and chunk PDF documents
for use as context in LLM prompts.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF


@dataclass
class PDFContent:
    """Extracted content from a PDF document.

    Attributes:
        text: Full text of the PDF concatenated across all pages.
        pages: List of per-page text strings.
        metadata: Dictionary of document metadata (e.g. page_count, author).
    """

    text: str
    pages: list[str]
    metadata: dict[str, Any]


def validate_pdf(path: str | pathlib.Path) -> bool:
    """Check whether *path* points to a valid, readable (non-encrypted) PDF.

    Returns ``True`` only when the file exists, can be opened by PyMuPDF,
    and is not password-protected.  Returns ``False`` for missing, corrupted,
    encrypted, or non-PDF files.
    """
    path = pathlib.Path(path)
    if not path.exists():
        return False
    try:
        doc = fitz.open(str(path))
        try:
            if not doc.is_pdf:
                return False
            if doc.is_encrypted:
                return False
            if doc.page_count < 1:
                return False
            doc[0].get_text()
            return True
        finally:
            doc.close()
    except Exception:
        return False


def extract_pdf_text(path: str | pathlib.Path) -> PDFContent:
    """Extract text from a PDF file and return a :class:`PDFContent`.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If the file is corrupted, password-protected, or otherwise
            unreadable — with a human-friendly error message.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path} does not exist")

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ValueError(
            f"Cannot open '{path.name}': the file is corrupt or not a valid PDF"
        ) from exc

    try:
        if not doc.is_pdf:
            raise ValueError(
                f"Cannot open '{path.name}': the file is not a valid PDF"
            )
        if doc.is_encrypted:
            raise ValueError(
                f"Cannot read '{path.name}': the PDF is password-protected / encrypted"
            )

        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())

        full_text = "\n".join(pages)

        metadata: dict[str, Any] = {
            "page_count": doc.page_count,
        }
        # Include standard PDF metadata when available
        doc_meta = doc.metadata
        if doc_meta:
            for key in ("title", "author", "subject", "creator", "producer"):
                val = doc_meta.get(key)
                if val:
                    metadata[key] = val

        return PDFContent(text=full_text, pages=pages, metadata=metadata)
    finally:
        doc.close()


def chunk_pdf_for_context(
    content: PDFContent, chunk_size: int = 4000
) -> list[str]:
    """Split *content*.text into chunks of at most *chunk_size* characters.

    Splitting is done on whitespace boundaries where possible so that words
    are not cut in half.  Returns an empty list when the text is empty.
    """
    text = content.text
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = start + chunk_size
        if end >= length:
            chunks.append(text[start:])
            break

        # Try to break on whitespace
        split_at = text.rfind(" ", start, end)
        if split_at <= start:
            # No whitespace found; hard-cut at chunk_size
            split_at = end

        chunks.append(text[start:split_at])
        start = split_at
        # Skip the space we split on
        if start < length and text[start] == " ":
            start += 1

    return chunks
