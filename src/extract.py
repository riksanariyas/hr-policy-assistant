from pathlib import Path

from docx import Document
from pypdf import PdfReader

SUPPORTED_TYPES = {".txt", ".pdf", ".docx"}


def extract_text(file_path):
    """Read a TXT, PDF or DOCX file and return its text."""
    path = Path(file_path)
    ext = path.suffix.lower()

    # Rule: only supported file types are accepted
    if ext not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported file type '{ext}'. Allowed: PDF, DOCX, TXT."
        )

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        if ext == ".txt":
            text = path.read_text(encoding="utf-8-sig")
        elif ext == ".pdf":
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:  # .docx
            doc = Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        raise ValueError(f"Could not read '{path.name}': {e}")

    text = text.strip()
    if not text:
        raise ValueError(f"'{path.name}' has no readable text.")
    return text