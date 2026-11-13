from pathlib import Path

from src.extract import extract_text
from src.chunk import chunk_text

folder = Path("sample_policies")
total = 0

for file in sorted(folder.iterdir()):
    text = extract_text(file)
    chunks = chunk_text(text, file.name)
    total += len(chunks)
    longest = max(len(c["text"]) for c in chunks)
    print(f"{file.name}: {len(chunks)} chunks, longest {longest} characters")
    for c in chunks:
        assert c["text"].strip(), "Empty chunk found"
        print("    -", c["section"])

print("Total chunks:", total)