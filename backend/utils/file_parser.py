import io
from typing import Union


def parse_file(content: bytes, ext: str) -> str:
    """Parse file bytes into plain text based on extension."""
    ext = ext.lower()

    if ext == ".txt":
        return _parse_txt(content)
    elif ext == ".pdf":
        return _parse_pdf(content)
    elif ext in (".docx", ".doc"):
        return _parse_docx(content)
    else:
        raise ValueError(f"Unsupported extension: {ext}")


def _parse_txt(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode text file with common encodings.")


def _parse_pdf(content: bytes) -> str:
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        result = "\n\n".join(pages).strip()
        if not result:
            raise ValueError("PDF contains no extractable text (possibly scanned image).")
        return result
    except ImportError:
        raise ImportError("PyPDF2 is not installed. Run: pip install PyPDF2")


def _parse_docx(content: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        result = "\n\n".join(paragraphs).strip()
        if not result:
            raise ValueError("DOCX file contains no text content.")
        return result
    except ImportError:
        raise ImportError("python-docx is not installed. Run: pip install python-docx")
