import sys
from search import search_chunks
from prompt_builder import build_prompt, estimate_tokens

# ---------------------------------------------------------------------------
# Test queries
# ---------------------------------------------------------------------------

TEST_QUERIES = [
    "Qual o prazo de devolução para mercadorias não perigosas?",
    "Qual o SLA de resolução para cliente Gold?",
    "Como calcular o frete especial para carga de 600kg na Região Norte?",
    "Quais são os multiplicadores regionais para frete especial?",
    "O que o cliente precisa fazer para abrir um chamado de devolução?",
]

SEPARATOR = "-" * 80

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests(output_path: str = "test_results.txt") -> None:
    lines: list[str] = []

    def emit(text: str = "") -> None:
        """Print to stdout and buffer for file output."""
        print(text)
        lines.append(text)

    for i, query in enumerate(TEST_QUERIES, start=1):
        emit(f"=== TESTE {i} — {query} ===")

        # --- Retrieval
        chunks = search_chunks(query, n_results=5)

        # Retrieval table
        emit(f"\n{'RANK':<5} {'SOURCE':<40} {'SECTION':<35} {'SCORE'}")
        emit(f"{'-' * 5} {'-' * 40} {'-' * 35} {'-' * 8}")
        for rank, chunk in enumerate(chunks, start=1):
            emit(
                f"{rank:<5} {chunk['source']:<40} "
                f"{chunk['section_title'][:34]:<35} "
                f"{chunk['similarity_score']:.4f}"
            )

        # --- Prompt assembly
        prompt = build_prompt(query, chunks)
        token_count = estimate_tokens(prompt)

        emit(f"\nPROMPT MONTADO (para enviar ao LLM):")
        emit(prompt)
        emit(f"\nEstimativa de tokens: {token_count}")
        emit(SEPARATOR)
        emit()

    # Write buffered output to file
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    total = len(TEST_QUERIES)
    summary = f"{total} testes concluídos. Resultados salvos em {output_path}"
    print(summary)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_tests()
