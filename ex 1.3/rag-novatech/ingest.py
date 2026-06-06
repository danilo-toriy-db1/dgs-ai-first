"""
RAG ingestion pipeline for NovaTech logistics documents.

Chunking strategy — SEMANTIC / HEADER-BASED:
  NovaTech documents are structured with clear section headers (H1/H2/H3).
  User questions map naturally to specific sections — e.g. "return policy"
  maps to "Política de Devolução". Header-based chunking preserves semantic
  coherence that fixed-size chunking would destroy, keeping each retrieved
  chunk self-contained and topically focused.

  Primary split : by markdown headers (lines starting with #, ## or ###).
  Secondary split: sections that exceed ~450 words (~600 tokens) are further
                   split by paragraph, with a 50-token (~37-word) overlap
                   between consecutive sub-chunks.
"""

import os
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DOCS_DIR = Path("anexo-a-documentos-individuais")
CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "novatech_docs"
MODEL_NAME = "all-MiniLM-L6-v2"

MAX_WORDS_PER_CHUNK = 450          # ~600 tokens
OVERLAP_TOKENS = 50                # ~37 words
OVERLAP_WORDS = int(OVERLAP_TOKENS * 0.75)

HEADER_RE = re.compile(r"^#{1,3}\s+(.+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def word_count(text: str) -> int:
    return len(text.split())


def token_estimate(text: str) -> int:
    return int(word_count(text) / 0.75)


def split_by_headers(content: str) -> list[tuple[str, str]]:
    """
    Split a markdown document into (section_title, section_text) pairs
    using H1/H2/H3 headers as boundaries.
    """
    sections: list[tuple[str, str]] = []
    last_title = "Introduction"
    last_start = 0

    for match in HEADER_RE.finditer(content):
        section_text = content[last_start:match.start()].strip()
        if section_text:
            sections.append((last_title, section_text))
        last_title = match.group(1).strip()
        last_start = match.end()

    # Tail section after the last header
    tail = content[last_start:].strip()
    if tail:
        sections.append((last_title, tail))

    return sections


def split_by_paragraphs_with_overlap(
    section_title: str, text: str
) -> list[tuple[str, str]]:
    """
    Further split a large section by paragraphs, maintaining a word-level
    overlap of ~OVERLAP_WORDS between consecutive chunks.
    Returns list of (section_title, chunk_text).
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[tuple[str, str]] = []
    current_words: list[str] = []

    for para in paragraphs:
        para_words = para.split()
        current_words.extend(para_words)

        if len(current_words) >= MAX_WORDS_PER_CHUNK:
            chunks.append((section_title, " ".join(current_words)))
            # Keep the last OVERLAP_WORDS as context for the next chunk
            current_words = current_words[-OVERLAP_WORDS:]

    if current_words:
        chunks.append((section_title, " ".join(current_words)))

    return chunks if chunks else [(section_title, text)]


def build_chunks(filename: str, content: str) -> list[dict]:
    """
    Apply semantic chunking strategy and return a list of chunk dicts
    with text + metadata.
    """
    sections = split_by_headers(content)
    chunks: list[dict] = []
    chunk_index = 0

    for section_title, section_text in sections:
        if word_count(section_text) > MAX_WORDS_PER_CHUNK:
            sub_chunks = split_by_paragraphs_with_overlap(section_title, section_text)
        else:
            sub_chunks = [(section_title, section_text)]

        for title, text in sub_chunks:
            chunks.append(
                {
                    "text": text,
                    "metadata": {
                        "source": filename,
                        "section_title": title,
                        "chunk_index": chunk_index,
                        "token_estimate": token_estimate(text),
                    },
                }
            )
            chunk_index += 1

    return chunks


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def main() -> None:
    # -- Embedding model
    print(f"Loading embedding model '{MODEL_NAME}' ...")
    model = SentenceTransformer(MODEL_NAME)

    # -- ChromaDB persistent client
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"No .md files found in '{DOCS_DIR}'. Exiting.")
        return

    total_docs = 0
    total_chunks = 0

    for md_path in md_files:
        filename = md_path.name
        print(f"\nProcessing: {filename}")

        try:
            content = md_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"  [ERROR] Could not read '{filename}': {exc}")
            continue

        chunks = build_chunks(filename, content)
        print(f"  → {len(chunks)} chunk(s) created")

        # Generate embeddings for all chunks in this file at once
        texts = [c["text"] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        # Build unique IDs: <stem>_chunk_<index>
        stem = md_path.stem.lower()
        ids = [f"{stem}_chunk_{c['metadata']['chunk_index']}" for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        total_docs += 1
        total_chunks += len(chunks)

    # -- Summary
    collection_size = collection.count()
    print("\n" + "=" * 50)
    print("Ingestion complete.")
    print(f"  Documents processed : {total_docs}")
    print(f"  Total chunks created: {total_chunks}")
    print(f"  Collection size     : {collection_size} document(s) in '{COLLECTION_NAME}'")
    print("=" * 50)


if __name__ == "__main__":
    main()
