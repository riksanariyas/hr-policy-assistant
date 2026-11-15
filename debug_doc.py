import sys
from pathlib import Path

from src import store
from src.chunk import chunk_text
from src.extract import extract_text

path = Path("sample_policies") / sys.argv[1]
question = sys.argv[2]

text = extract_text(path)
chunks = chunk_text(text, path.name)
print(f"Characters read: {len(text)}")
print(f"Chunks made: {len(chunks)}")
for i, c in enumerate(chunks, 1):
    print(f"  {i}. [{len(c['text'])} chars] {c['section']}")

print()
print("Top matches for:", question)
for h in store.search(question, k=3):
    print(f"  score {h['score']}  {h['source']} - {h['section']}")