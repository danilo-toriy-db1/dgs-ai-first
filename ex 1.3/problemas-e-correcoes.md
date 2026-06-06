# Problemas Identificados e Propostas de Correção — Pipeline RAG NovaTech

> Este documento cobre os dois problemas mais críticos encontrados nos 5 testes do pipeline,
> com análise de causa raiz, evidência dos testes, e proposta de correção concreta e
> implementável. Um terceiro problema de menor gravidade é listado como observação ao final.

---

## Problema 1 — Chunking por seção isola conteúdo de resposta do texto recuperável pelo retriever

### Descrição

O pipeline usa chunking semântico por header markdown, onde cada seção de um documento vira
um chunk independente. O problema é que seções de **Objetivo** — que descrevem o que o
documento faz — são semanticamente mais próximas das queries do usuário do que as seções de
**conteúdo** — que contêm tabelas, fórmulas e valores numéricos.

Um usuário pergunta "Como calcular o frete especial para 600kg na Região Norte?". O embedding
desta query é mais próximo do texto "Definir a fórmula e os parâmetros para cálculo de frete
especial aplicável a cargas com peso acima de 500kg" (seção Objetivo) do que de "Valor do
frete = Valor base × Multiplicador regional × Fator de peso | Norte | 1,8" (seção Fórmula).
Palavras como "frete especial", "fórmula", "cálculo" e "500kg" aparecem no Objetivo em
linguagem natural; a seção de fórmulas é densa em números e nomes de região.

Resultado: o topo do ranking de retrieval fica ocupado com seções introdutórias que confirmam
que o documento é sobre o tema, mas não fornecem a informação que o usuário precisa.

### Evidência nos testes

**Teste 3 (frete 600kg Região Norte):** 5/5 chunks recuperados eram seções de "Objetivo" —
nenhum continha a fórmula ou os multiplicadores regionais. Scores relativamente altos
(máximo 0.3495) para chunks completamente inúteis.

**Teste 1 (prazo devolução):** Chunks de "Prazo de entrega de frete especial" apareceram
no top-3 de uma query sobre devolução — colisão de vocabulário causada pela palavra "prazo"
presente em ambos os contextos.

### Estratégia de correção — Parent-Child Retrieval (Retrieval Hierárquico)

A ideia é separar a unidade de **busca** (pequena, rica em linguagem natural) da unidade de
**contexto** (maior, contém a resposta completa).

**Como funciona:**
- Cada documento é indexado em dois níveis:
  - **Filho (child):** seções individuais — unidades de busca. O retriever compara queries
    contra esses chunks pequenos.
  - **Pai (parent):** documento completo ou grupo de seções relacionadas — unidade de contexto.
    O que é enviado ao LLM depois que o retriever encontra os filhos relevantes.

**Implementação em `ingest.py`:**

```python
# Ao indexar, adicionar campo parent_id em cada chunk filho
for i, chunk in enumerate(chunks):
    metadata = {
        "source": filename,
        "section_title": chunk.section_title,
        "chunk_index": i,
        "parent_id": filename,       # ← novo campo
        "chunk_type": "child"        # ← novo campo
    }

# Indexar também o documento completo como chunk pai
parent_metadata = {
    "source": filename,
    "section_title": "DOCUMENTO_COMPLETO",
    "chunk_index": -1,
    "parent_id": filename,
    "chunk_type": "parent"
}
```

**Implementação em `search.py`:**

```python
def search_chunks_with_parent(query: str, n_results: int = 5) -> list[dict]:
    # 1. Buscar chunks filhos normalmente
    child_results = collection.query(
        query_embeddings=[embed(query)],
        n_results=n_results,
        where={"chunk_type": "child"}   # ← busca apenas filhos
    )
    
    # 2. Para cada filho encontrado, buscar o pai correspondente
    parent_ids = set(r["parent_id"] for r in child_results)
    parent_chunks = collection.get(
        where={"parent_id": {"$in": list(parent_ids)}, "chunk_type": "parent"}
    )
    
    # 3. Retornar os pais (com mais contexto) ao invés dos filhos
    return parent_chunks
```

**O que muda:** em vez de enviar ao LLM apenas a seção de Objetivo (que foi a mais similar à
query), o pipeline envia o documento completo ou um grupo de seções. O retriever continua
encontrando os documentos certos via similaridade semântica, mas o LLM recebe contexto
suficiente para localizar a resposta na seção correta.

**Trade-off:** chunks pai são maiores (mais tokens por chunk), o que reduz o número de
documentos diferentes que cabem no contexto. Para a NovaTech, com documentos de tamanho
moderado (~10 páginas = ~2.500 tokens por documento), enviar 2–3 documentos pai em vez de
5 seções fragmentadas é um tradeoff favorável.

---

## Problema 2 — Documentos desatualizados competem com versões vigentes sem nenhum sinal de autoridade

### Descrição

O pipeline ingere todos os documentos tratando-os como igualmente válidos. Quando existem
múltiplas versões do mesmo documento (PROC-042-v1 e PROC-042-v2), ambas são indexadas e
ambas aparecem nos resultados de busca. O LLM recebe valores conflitantes sem nenhum
metadado que indique qual versão é vigente.

Este não é um problema teórico — é um risco operacional documentado: no Teste 4, os
multiplicadores para a Região Norte apareceram como **1,6** (v1 — desatualizado) e **1,8**
(v2 — vigente desde novembro/2023). Um erro de 12,5% no multiplicador regional em cotações
de frete representa perda de receita direta para a NovaTech em cada cotação afetada.

O Claude detectou o conflito e escalou corretamente neste teste — mas depender do LLM para
identificar inconsistências em dados operacionais críticos não é uma estratégia sustentável.
A detecção de conflito deve ocorrer antes do LLM, na camada de retrieval.

### Evidência nos testes

**Teste 4 (multiplicadores regionais):**

| Chunk | Origem | Multiplicador Norte | Status |
|-------|--------|---------------------|--------|
| Chunk 1 | anexo-a seção 2.1 (nov/2023) | 1,8 | ✅ Vigente |
| Chunk 2 | anexo-a seção 2.1 (s/ data) | 1,6 | ❌ Desatualizado |
| Chunk 4 | PROC-042-v1 seção 2 | Fator de peso: 1.2/1.5 | ❌ Desatualizado |
| Chunk 3 | PROC-042-v2 seção 2 | Fator de peso: 1.15/1.4 | ✅ Vigente |

Dois valores diferentes para a mesma variável no mesmo contexto de resposta. O sistema
tratou v1 e v2 como fontes de igual autoridade.

**Teste 3 (frete 600kg Norte):** O Claude identificou proativamente a existência das duas
versões e recomendou usar a v2 — mas esse comportamento correto depende de o LLM reconhecer
a nomenclatura "v1/v2" como indicativo de versão. Documentos versionados com datas em vez de
sufixos numéricos não teriam esse sinal disponível.

### Estratégia de correção — Metadados de vigência + filtro na query

**Passo 1 — Enriquecer metadados durante a ingestão (`ingest.py`):**

```python
import re
from datetime import datetime

def extract_doc_status(filename: str, content: str) -> dict:
    """
    Infere o status do documento a partir do nome do arquivo e do conteúdo.
    """
    # Detectar versão pelo nome do arquivo
    version_match = re.search(r'v(\d+)', filename.lower())
    version = int(version_match.group(1)) if version_match else 1
    
    # Detectar data de atualização no conteúdo
    date_match = re.search(r'atualiz\w+.*?(\d{2}/\d{4}|\d{4}-\d{2}-\d{2})', 
                           content, re.IGNORECASE)
    last_updated = date_match.group(1) if date_match else "desconhecida"
    
    # Identificar o documento base (sem sufixo de versão)
    base_name = re.sub(r'-v\d+.*', '', filename.replace('.md', ''))
    
    return {
        "doc_version": version,
        "doc_base_name": base_name,         # ← agrupa versões do mesmo doc
        "last_updated": last_updated,
        "status": "active"                   # ← padrão; será corrigido no Passo 2
    }
```

**Passo 2 — Marcar versões obsoletas após ingestão completa:**

```python
def deprecate_old_versions(collection):
    """
    Para cada documento base, mantém apenas a versão mais alta como 'active'.
    As demais recebem status 'deprecated'.
    """
    all_docs = collection.get(include=["metadatas"])
    
    # Agrupar por documento base
    groups = {}
    for meta in all_docs["metadatas"]:
        base = meta.get("doc_base_name", meta["source"])
        if base not in groups:
            groups[base] = []
        groups[base].append(meta)
    
    # Para cada grupo, manter ativo apenas o de maior versão
    for base, versions in groups.items():
        if len(versions) > 1:
            max_version = max(v["doc_version"] for v in versions)
            for v in versions:
                if v["doc_version"] < max_version:
                    # Atualizar metadado para deprecated
                    collection.update(
                        ids=[v["chunk_id"]],
                        metadatas=[{**v, "status": "deprecated"}]
                    )
```

**Passo 3 — Filtrar por status na busca (`search.py`):**

```python
def search_chunks(query: str, n_results: int = 5,
                  active_only: bool = True) -> list[dict]:
    
    where_filter = {}
    if active_only:
        where_filter["status"] = "active"   # ← exclui versões deprecated
    
    # Filtro adicional: excluir chunks com score abaixo do mínimo
    results = collection.query(
        query_embeddings=[embed(query)],
        n_results=n_results,
        where=where_filter if where_filter else None
    )
    
    # Remover chunks com score negativo ou abaixo de limiar mínimo
    filtered = [r for r in results if r["similarity_score"] > 0.05]
    
    return filtered
```

**O que muda:** o Teste 4 com esta correção retornaria apenas chunks de PROC-042-v2 e da
tabela atualizada de novembro/2023, eliminando o conflito antes de chegar ao LLM. O Claude
não precisaria detectar e escalar o problema — receberia apenas dados vigentes.

**Esforço de implementação estimado:** menos de uma tarde de trabalho. As bibliotecas
ChromaDB e sentence-transformers já suportam filtragem por metadados nativamente via
o parâmetro `where` nas queries.

---

## Observação Adicional — Score negativo incluído no contexto (Teste 4, Chunk 5)

**Problema:** No Teste 4, o Chunk 5 (POL-001 seção 3.4 — Devoluções parciais) foi incluído
no contexto enviado ao LLM com score **-0.0057**. Um score negativo indica que o chunk é
semanticamente oposto à query — sua presença no contexto é ruído puro.

**Correção imediata (1 linha de código):**

```python
# Em search.py, após a query ao ChromaDB:
results = [r for r in results if r["similarity_score"] > 0.05]
```

Um limiar mínimo de 0.05 exclui automaticamente chunks com scores negativos ou muito próximos
de zero. Este filtro deveria ser padrão em qualquer pipeline de produção.

---

## Resumo das Correções

| Problema | Gravidade | Correção | Esforço |
|----------|-----------|----------|---------|
| Seções de Objetivo recuperadas em vez de seções de conteúdo | Alta | Parent-child retrieval | 1–2 dias |
| Versões obsoletas competindo com vigentes | Crítica (risco de dado errado ao cliente) | Metadados de vigência + filtro `status: active` | Menos de 1 tarde |
| Chunk com score negativo incluído no contexto | Baixa | Limiar mínimo de score (0.05) | 1 linha de código |

**Prioridade de implementação recomendada:**
1. **Imediato:** filtro de score mínimo (1 linha, sem risco)
2. **Sprint atual:** metadados de vigência (impacto operacional direto, esforço baixo)
3. **Sprint seguinte:** parent-child retrieval (melhora estrutural do pipeline, esforço moderado)

---

## Reflexão: RAG é um Sistema de Engenharia de Dados

Os problemas encontrados ilustram uma premissa fundamental que o exercício propõe avaliar:
**RAG não é apenas "chamar uma API de LLM com documentos"**.

Os guardrails funcionaram perfeitamente em todos os 5 testes — o Claude nunca inventou dados,
sempre sinalizou limitações, sempre escalou quando necessário. A camada de geração está sólida.

O gargalo é a camada de dados: chunking que isola conteúdo de resposta, ausência de
metadados de vigência, falta de limiar mínimo de score. Estes são problemas de engenharia de
dados, não de prompt engineering. Melhorar o prompt não teria corrigido nenhum dos três
problemas documentados acima.

Para um sistema em produção na NovaTech — com 320 chamados/dia e meta de reduzir tempo de
busca de 12 para menos de 2 minutos — a qualidade do retrieval determina o retorno do
investimento. Um pipeline que só funciona bem em 1 de 5 queries não atinge essa meta, por
melhor que seja o LLM na ponta.
