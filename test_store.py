from pathlib import Path

from src import store

# 1. Ingest every file in sample_policies
for file in sorted(Path("sample_policies").iterdir()):
    n = store.ingest_file(file)
    print(f"Stored {n} chunks from {file.name}")

print("Total chunks in Chroma:", store.count())

# 2. Ingest again: the count must NOT grow (no duplicates)
for file in sorted(Path("sample_policies").iterdir()):
    store.ingest_file(file)
print("Total after re-ingest:", store.count())

# 3. Search tests
questions = [
    "How many casual leaves do I get per year?",
    "Do I need a medical certificate for sick leave?",
    "What is the notice period after confirmation?",
    "How is overtime paid?",
    "Does the company provide health insurance?",
]
for q in questions:
    print("\nQ:", q)
    for r in store.search(q, k=3):
        print(f"   {r['score']}  {r['source']} - {r['section']}")

# 4. Delete test: removed content must not come back
store.delete_source("holiday_list.txt")
print("\nAfter deleting holiday_list.txt:", store.count(), "chunks")
for r in store.search("How many paid holidays are there?", k=3):
    print(f"   {r['score']}  {r['source']} - {r['section']}")

store.ingest_file("sample_policies/holiday_list.txt")  # put it back
print("Restored. Total:", store.count())