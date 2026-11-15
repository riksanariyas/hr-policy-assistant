import re

MAX_CHARS = 1000  # about 250 tokens, the length the embedding model reads well
NUMBERED = re.compile(r"^\d+\.\s")


def _units(text, limit):
    """Break text into small pieces: lines first, then sentences, then hard cuts."""
    units = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) <= limit:
            units.append(line)
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            sentence = sentence.strip()
            while len(sentence) > limit:  # one giant sentence: cut at a space
                cut = sentence.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                units.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                units.append(sentence)
    return units


def _pack(text, limit=MAX_CHARS):
    """Join the small pieces back together into chunks of at most `limit` characters."""
    pieces, current = [], ""
    for unit in _units(text, limit):
        if current and len(current) + 1 + len(unit) > limit:
            pieces.append(current)
            current = unit
        else:
            current = f"{current}\n{unit}" if current else unit
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text, source):
    """Split a document into sections. Each chunk keeps its source and heading."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        return []
    doc_title = blocks[0].split("\n")[0].strip()

    structured = any(NUMBERED.match(b.split("\n")[0].strip()) for b in blocks)
    chunks = []

    if structured:
        # Numbered sections ("1. Casual Leave"): same behaviour as before
        for block in blocks:
            first_line = block.split("\n")[0].strip()
            is_numbered = NUMBERED.match(first_line)

            if not is_numbered and "\n" not in block:
                continue  # title-only block, nothing to search

            if is_numbered:
                section = re.sub(r"^\d+\.\s*", "", first_line)
            else:
                section = first_line[:60]  # intro block, e.g. the disclaimer

            pieces = [block] if len(block) <= MAX_CHARS else _pack(block)
            for n, piece in enumerate(pieces, 1):
                label = section if n == 1 else f"{section} (part {n})"
                chunks.append(
                    {
                        "source": source,
                        "section": label,
                        "text": f"{doc_title} - {label}\n{piece}",
                    }
                )
    else:
        # No numbered sections (typical for PDF, DOCX or free text): split by size
        for n, piece in enumerate(_pack("\n\n".join(blocks)), 1):
            first = piece.split("\n")[0].strip()
            if len(first) <= 80 and not first.endswith("."):
                label = first[:60]  # looks like a heading
            else:
                label = f"Part {n}"
            chunks.append(
                {
                    "source": source,
                    "section": label,
                    "text": f"{doc_title} - {label}\n{piece}",
                }
            )
    return chunks