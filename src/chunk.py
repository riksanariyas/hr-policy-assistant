import re


def chunk_text(text, source):
    """Split a document into sections. Each chunk keeps its source and heading."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    doc_title = blocks[0].split("\n")[0].strip()

    chunks = []
    for block in blocks:
        first_line = block.split("\n")[0].strip()
        is_numbered = re.match(r"^\d+\.\s", first_line)

        if not is_numbered and "\n" not in block:
            continue  # title-only block, nothing to search

        if is_numbered:
            section = re.sub(r"^\d+\.\s*", "", first_line)  # "1. Casual Leave" -> "Casual Leave"
        else:
            section = first_line[:60]  # intro block, e.g. the disclaimer

        chunks.append(
            {
                "source": source,
                "section": section,
                "text": f"{doc_title} - {section}\n{block}",
            }
        )
    return chunks