from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from src.chunk import chunk_text
from src.extract import extract_text

_model = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path="chroma_db")
        _collection = client.get_or_create_collection("policies")
    return _collection


def count():
    """Number of chunks stored."""
    return _get_collection().count()


def delete_source(source):
    """Remove every chunk that came from this file name."""
    _get_collection().delete(where={"source": source})


def ingest_file(file_path):
    """Extract, chunk, embed and store one file. Re-ingesting replaces old chunks."""
    path = Path(file_path)
    text = extract_text(path)
    chunks = chunk_text(text, path.name)

    delete_source(path.name)  # prevents duplicates

    embeddings = _get_model().encode(
        [c["text"] for c in chunks], normalize_embeddings=True
    ).tolist()

    _get_collection().add(
        ids=[f"{path.name}::{i}" for i in range(len(chunks))],
        documents=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[{"source": c["source"], "section": c["section"]} for c in chunks],
    )
    return len(chunks)


def list_sources():
    """Return {file name: number of sections} for every stored document."""
    data = _get_collection().get(include=["metadatas"])
    counts = {}
    for meta in data["metadatas"]:
        counts[meta["source"]] = counts.get(meta["source"], 0) + 1
    return dict(sorted(counts.items()))

def search(query, k=3):
    """Return the k closest chunks, each with source, section and a 0-1 score."""
    embedding = _get_model().encode([query], normalize_embeddings=True).tolist()
    res = _get_collection().query(query_embeddings=embedding, n_results=k)

    results = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        results.append(
            {
                "text": doc,
                "source": meta["source"],
                "section": meta["section"],
                "score": round(1 - dist / 2, 3),  # higher = closer match
            }
        )
    return results