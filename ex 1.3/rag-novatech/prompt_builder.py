from search import search_chunks

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
Você é o Assistente Operacional NovaTech, um sistema de apoio à decisão
usado exclusivamente por atendentes humanos da NovaTech Logística.

Seu papel é localizar e apresentar informações contidas nos chunks de
documentação interna fornecidos. Responda APENAS com base nos chunks
fornecidos — não utilize conhecimento externo.

REGRAS INVIOLÁVEIS:
1. Sempre cite a fonte exata no formato: (CÓDIGO-DO-DOCUMENTO, seção X.X)
2. Nunca invente prazos, valores ou condições que não estejam nos chunks
3. Se a informação não estiver nos chunks, diga explicitamente e recomende
   escalar para o supervisor de atendimento
4. Responda em português formal e acessível
5. Nunca inclua identificadores internos como "Chunk 1", "Chunk A" nas citações

FORMATO DA RESPOSTA:
[1] RESPOSTA DIRETA: responda a pergunta em até 3 frases
[2] DETALHAMENTO: qualificações, exceções ou contexto adicional (se necessário).
    Se não houver, escreva "[2] Não aplicável para esta consulta."
[3] FONTES E OBSERVAÇÕES: liste as fontes e sinalize qualquer limitação
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_prompt(query: str, chunks: list[dict]) -> str:
    """
    Assembles the full prompt to send to the LLM.

    Chunk ordering uses anti-lost-in-middle strategy:
    - Position 0      : chunk with highest similarity score
    - Positions 1…n-2 : remaining chunks in descending score order
    - Position n-1    : chunk with second highest similarity score

    This ensures the most relevant content appears at the boundaries of the
    context window, where LLMs have stronger attention.

    Format:
    [SYSTEM PROMPT]
    ---
    DOCUMENTAÇÃO RECUPERADA:
    --- CHUNK 1 de N ---
    Fonte: <source> | Seção: <section_title> | Score: <score>
    <chunk_text>
    ...
    ---
    PERGUNTA DO ATENDENTE: <query>
    """
    if not chunks:
        ordered = []
    elif len(chunks) == 1:
        ordered = chunks[:]
    else:
        # Sort descending by similarity score
        sorted_chunks = sorted(chunks, key=lambda c: c["similarity_score"], reverse=True)
        best = sorted_chunks[0]
        second_best = sorted_chunks[1]
        rest = sorted_chunks[2:]  # already in descending order

        # Anti-lost-in-middle: best first, second-best last
        ordered = [best] + rest + [second_best]

    n = len(ordered)
    chunk_blocks: list[str] = []

    for i, chunk in enumerate(ordered, start=1):
        header = (
            f"--- CHUNK {i} de {n} ---\n"
            f"Fonte: {chunk['source']} | "
            f"Seção: {chunk['section_title']} | "
            f"Score: {chunk['similarity_score']:.4f}"
        )
        chunk_blocks.append(f"{header}\n{chunk['chunk_text']}")

    retrieved_section = "\n\n".join(chunk_blocks)

    prompt = (
        f"{SYSTEM_PROMPT.strip()}\n"
        "---\n"
        "DOCUMENTAÇÃO RECUPERADA:\n"
        f"{retrieved_section}\n"
        "---\n"
        f"PERGUNTA DO ATENDENTE: {query}"
    )

    return prompt


def estimate_tokens(text: str) -> int:
    """Estimates token count using rule: word_count / 0.75"""
    return int(len(text.split()) / 0.75)


# ---------------------------------------------------------------------------
# Entry point — demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_query = "Qual é o prazo para devolução de mercadorias avariadas?"

    print(f'Searching for: "{sample_query}"\n')
    chunks = search_chunks(sample_query, n_results=5)

    prompt = build_prompt(sample_query, chunks)
    token_count = estimate_tokens(prompt)

    print(prompt)
    print("\n" + "=" * 60)
    print(f"Estimated token count: {token_count}")
    print("=" * 60)
