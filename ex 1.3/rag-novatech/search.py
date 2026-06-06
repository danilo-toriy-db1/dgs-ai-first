import chromadb
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "novatech_docs"
MODEL_NAME = "all-MiniLM-L6-v2"

# Module-level singletons (initialised lazily on first call)
_model: SentenceTransformer | None = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = client.get_collection(name=COLLECTION_NAME)
    return _collection


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_chunks(query: str, n_results: int = 5) -> list[dict]:
    """
    Searches ChromaDB for the most similar chunks to the query.
    Returns a list of dicts with keys:
      - chunk_text: full text of the chunk
      - source: source filename from metadata
      - section_title: section title from metadata
      - similarity_score: float (1 - distance), higher = more similar
      - chunk_index: int from metadata
    """
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode(query).tolist()

    response = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    results: list[dict] = []
    documents = response["documents"][0]
    metadatas = response["metadatas"][0]
    distances = response["distances"][0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        results.append(
            {
                "chunk_text": doc,
                "source": meta.get("source", ""),
                "section_title": meta.get("section_title", ""),
                "similarity_score": round(1 - dist, 4),
                "chunk_index": int(meta.get("chunk_index", -1)),
            }
        )

    return results


def display_results(results: list[dict]) -> None:
    """Prints results formatted as: rank, source, section, score, text preview (200 chars)"""
    if not results:
        print("No results found.")
        return

    print(f"\n{'=' * 60}")
    print(f"{'RANK':<5} {'SOURCE':<35} {'SCORE':<8} SECTION")
    print(f"{'-' * 60}")

    for rank, result in enumerate(results, start=1):
        source = result["source"]
        section = result["section_title"]
        score = result["similarity_score"]
        preview = result["chunk_text"][:200].replace("\n", " ")
        chunk_idx = result["chunk_index"]

        print(f"[{rank}]  Source  : {source}  (chunk #{chunk_idx})")
        print(f"     Section : {section}")
        print(f"     Score   : {score:.4f}")
        print(f"     Preview : {preview}{'...' if len(result['chunk_text']) > 200 else ''}")
        print(f"{'-' * 60}")


# ---------------------------------------------------------------------------
# Entry point — test search
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    query = "prazo de devolução de mercadorias"
    print(f"Query: \"{query}\"")

    results = search_chunks(query, n_results=5)
    display_results(results)
