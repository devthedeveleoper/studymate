from pypdf import PdfReader


def extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    """
    Extract all text from a PDF file.

    Returns a tuple of (full_text, page_count).
    Concatenates text from all pages with double newlines between them.
    """
    reader = PdfReader(file_path)
    pages = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())

    full_text = "\n\n".join(pages)
    # remove NUL characters to prevent PostgreSQL/asyncpg DataError
    full_text = full_text.replace("\x00", "")
    return full_text, len(reader.pages)
