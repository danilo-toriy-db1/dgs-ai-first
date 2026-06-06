# Resultados dos 5 Testes — Pipeline RAG NovaTech

## Contexto do Pipeline

**Stack utilizada:**
- Linguagem: Python
- Embeddings: `sentence-transformers` — modelo `all-MiniLM-L6-v2`
- Vector store: ChromaDB (persistente local, pasta `chroma_db/`)
- Orquestração: scripts Python manuais (`ingest.py`, `search.py`, `prompt_builder.py`, `test_pipeline.py`)
- LLM de geração: Claude (via chat manual, conta corporativa)

**Estratégia de chunking adotada (justificada):**
Chunking semântico por seção de header markdown (H1, H2, H3). Cada seção se torna um chunk
independente. Seções acima de ~450 palavras (~600 tokens) são subdivididas por parágrafo com
overlap de ~50 tokens entre chunks consecutivos.

Justificativa: Os documentos da NovaTech possuem estrutura com cabeçalhos hierárquicos claros
(POL-001 seção 3.2, PROC-042 seção 2.1, SLA-2024 seção 5). Perguntas operacionais mapeiam
naturalmente para seções específicas — "prazo de devolução" mapeia para "seção 3. Devoluções",
não para o documento inteiro. Chunking fixo de 512 tokens quebraria seções no meio de tabelas
ou procedimentos, destruindo a coerência semântica que torna o retrieval preciso.

**Referência de scores (modelo `all-MiniLM-L6-v2`, similaridade de cosseno):**
- Acima de 0,50: correspondência semântica forte
- 0,30–0,50: correspondência razoável
- Abaixo de 0,30: correspondência fraca
- Negativo: dissimilaridade semântica (chunk oposto à query)

---

## Teste 1 — "Qual o prazo de devolução para mercadorias não perigosas?"

### Chunks Recuperados

| Rank | Fonte | Seção | Score | Relevante? |
|------|-------|-------|-------|------------|
| 1 | POL-001-politica-devolucao.md | 3.3. Procedimento de devolução | 0.2397 | ⚠️ Parcial |
| 2 | anexo-a-documentacao-simulada-novatech.md | 3. Prazo de entrega para frete especial | 0.1521 | ❌ Não |
| 3 | PROC-042-frete-especial-v1.md | 3. Prazo de entrega para frete especial | 0.1450 | ❌ Não |
| 4 | anexo-a-documentacao-simulada-novatech.md | 1. Objetivo | 0.1259 | ⚠️ Parcial |
| 5 | POL-001-politica-devolucao.md | 1. Objetivo | 0.1259 | ⚠️ Parcial |

**Avaliação dos scores:** Muito baixos (máximo 0.2397 — abaixo do limiar de correspondência
razoável). O retriever não encontrou correspondência semântica forte para esta query.

**Análise de relevância chunk a chunk:**

- **Chunk 1 (POL-001, seção 3.3 — Procedimento):** Contém o passo a passo do processo de
  devolução (portal, CT-e, fotos, triagem em 4h, coleta em 2 dias, reembolso em 5 dias), mas
  não especifica um prazo diferenciado para a categoria "mercadorias não perigosas". Parcialmente
  útil para contexto, não para a pergunta exata.

- **Chunks 2 e 3 (PROC-042 e anexo, seção "Prazo de entrega para frete especial"):**
  Completamente irrelevantes. Tratam de prazos de **entrega** de frete, não de **devolução**.
  Causa: colisão de vocabulário — a palavra "prazo" aparece em ambos os domínios, e o embedding
  da query se aproximou de documentos do domínio errado.

- **Chunks 4 e 5 (seções Objetivo):** Mencionam que a política "aplica-se a todos os tipos
  de cliente e categorias de carga, salvo exceções explicitamente listadas na seção 3" —
  contextualmente útil, mas não responde a pergunta.

**⚠️ Comparação com Anexo B (verificação manual recomendada):**
O chunk correto para esta query seria POL-001 seção 3.2 (exclusão de cargas perigosas — que
por implicação define o prazo padrão de 7 dias úteis para as não perigosas). Esta seção não
foi recuperada. Verificar no gabarito do Anexo B se POL-001 seção 3.2 consta como chunk
esperado para esta pergunta.

### Avaliação da Resposta do Claude

| Critério | Resultado | Detalhe |
|----------|-----------|---------|
| Resposta factualmente correta? | ✅ | Identificou que os chunks não tinham a distinção por tipo de carga |
| Citou fontes? | ✅ | POL-001 seções 1 e 3.3 |
| Guardrail 1 — citar fonte? | ✅ | Formato correto |
| Guardrail 2 — não inventar prazo? | ✅ | Não afirmou "7 dias" sem base nos chunks |
| Guardrail 3 — escalar quando incompleto? | ✅ | Recomendou escalonamento ao supervisor |
| Guardrail 4 — português formal? | ✅ | Linguagem adequada |

**Veredicto:** O pipeline falhou no retrieval (chunks errados, scores baixos), mas o Claude
aplicou corretamente todos os guardrails e degradou para "resposta honesta de ausência" em vez
de alucinação. Comportamento correto dado o contexto disponível.

---

## Teste 2 — "Qual o SLA de resolução para cliente Gold?"

### Chunks Recuperados

| Rank | Fonte | Seção | Score | Relevante? |
|------|-------|-------|-------|------------|
| 1 | FAQ-atendimento.md | Item 41 — SLA de resposta vs. resolução | 0.3480 | ✅ Sim |
| 2 | anexo-a-documentacao-simulada-novatech.md | 5. Medição e reportes | 0.3029 | ✅ Sim |
| 3 | anexo-a-documentacao-simulada-novatech.md | Perguntas selecionadas | 0.2497 | ⚠️ Parcial |
| 4 | FAQ-atendimento.md | Item 27 — Tracking parado | 0.2232 | ⚠️ Parcial |
| 5 | SLA-2024-tabela-sla-clientes.md | 5. Medição e reportes | 0.2010 | ✅ Sim |

**Avaliação dos scores:** Melhores do conjunto de testes (máximo 0.3480). Retrieval funcionou
razoavelmente bem para esta query.

**Análise de relevância chunk a chunk:**

- **Chunk 1 (FAQ Item 41):** Contém a resposta exata — "Gold tem 2h de resposta e 24h de
  resolução. Silver é 4h e 48h. Standard é 8h e 72h." Chunk correto no topo do ranking.

- **Chunks 2 e 5 (SLA-2024, seção 5):** Contêm a regra de medição e o detalhe crítico de que
  "o relógio de SLA não pausa para incidentes críticos de clientes Gold". Informação adicional
  relevante e corretamente recuperada.

- **Chunk 3 (Perguntas selecionadas):** Duplicata parcial do conteúdo do Chunk 1. Redundante,
  ocupa espaço de contexto mas não prejudica a resposta.

- **Chunk 4 (FAQ Item 27 — Tracking):** Parcialmente relevante — menciona que chamados de
  cliente Gold devem ser classificados como prioridade alta, mas o foco é em rastreamento,
  não em SLA. Ruído aceitável neste teste.

**⚠️ Comparação com Anexo B:** Chunks 1 e 5 são os candidatos corretos esperados. Verificar
no gabarito se SLA-2024 seção 3 (valores tabulares por tier) constava como chunk esperado
— não foi recuperado, mas o FAQ continha a informação equivalente.

### Avaliação da Resposta do Claude

| Critério | Resultado | Detalhe |
|----------|-----------|---------|
| Resposta factualmente correta? | ✅ | Gold: 24h resolução, 2h resposta |
| Citou fontes? | ✅ | FAQ Item 41 e SLA-2024 seção 5 |
| Identificadores internos na citação? | ✅ Ausentes | Nenhum "Chunk X" nas referências |
| Guardrail 1 — citar fonte? | ✅ | |
| Guardrail 2 — não inventar? | ✅ | |
| Guardrail 3 — escalar? | ✅ N/A | Informação completa nos chunks |
| Guardrail 4 — português formal? | ✅ | |
| Informação adicional de valor? | ✅ | Detalhou a regra de não-pausa para incidentes críticos Gold |

**Veredicto:** Melhor resultado do conjunto. Pipeline recuperou chunks corretos com scores
razoáveis, Claude respondeu com precisão e adicionou contexto operacional relevante (regra
de não-pausa). Único teste onde o pipeline funcionou de ponta a ponta sem ressalvas
significativas.

---

## Teste 3 — "Como calcular o frete especial para carga de 600kg na Região Norte?"

### Chunks Recuperados

| Rank | Fonte | Seção | Score | Relevante? |
|------|-------|-------|-------|------------|
| 1 | anexo-a-documentacao-simulada-novatech.md | 1. Objetivo | 0.3495 | ❌ Não |
| 2 | PROC-042-frete-especial-v1.md | 1. Objetivo | 0.3495 | ❌ Não |
| 3 | anexo-a-documentacao-simulada-novatech.md | 1. Objetivo (v2) | 0.2913 | ❌ Não |
| 4 | PROC-042-v2-frete-especial-revisado.md | 1. Objetivo | 0.2913 | ❌ Não |
| 5 | anexo-a-documentacao-simulada-novatech.md | Gaps identificados | 0.2817 | ❌ Não |

**Avaliação dos scores:** Paradoxo de retrieval — scores relativamente altos (máximo 0.3495),
mas todos os 5 chunks são de seções de **Objetivo**, não de fórmulas. O retriever identificou
os documentos corretos mas as seções erradas.

**Análise de relevância chunk a chunk:**

- **Chunks 1–4 (seções Objetivo):** Contêm variações de "Definir a fórmula e os parâmetros
  para cálculo de frete especial aplicável a cargas com peso acima de 500kg." Texto descritivo
  do objetivo do documento — não a fórmula em si. A seção com os multiplicadores (seção 2) não
  foi recuperada em nenhum dos 5 slots.

- **Chunk 5 (Gaps identificados):** Descreve lacunas da documentação da NovaTech. Semanticamente
  o mais distante da query, mas o embedding o trouxe de alguma forma — provavelmente por conter
  o texto "PROC-042" e "acima de 500kg" no contexto de gaps.

**Causa raiz identificada:** Seções de Objetivo contêm linguagem natural rica em palavras-chave
da query ("frete especial", "fórmula", "cálculo", "acima de 500kg", "parâmetros"). A seção 2,
que contém a fórmula e os multiplicadores, é composta predominantemente por números e nomes de
região — conteúdo que o modelo `all-MiniLM-L6-v2` representa de forma menos similar à frase
da query do que o texto descritivo do Objetivo. Este é o problema estrutural descrito no
Problema 1 das Propostas de Correção.

**⚠️ Comparação com Anexo B:** O chunk correto é PROC-042-v2 seção 2 (fórmula + tabela de
multiplicadores). Verificar no gabarito se esta seção consta como chunk esperado — nenhum dos
5 chunks recuperados a continha.

### Avaliação da Resposta do Claude

| Critério | Resultado | Detalhe |
|----------|-----------|---------|
| Resposta factualmente correta? | ✅ | Identificou corretamente que os chunks não tinham a fórmula |
| Não inventou fórmula? | ✅ | Não apresentou nenhum cálculo sem base |
| Guardrail 3 — escalar? | ✅ | Recomendou PROC-042-v2 completo |
| Informação adicional? | ✅ | Identificou o conflito entre v1 e v2 e alertou para usar a v2 revisada |

**Veredicto:** Falha de retrieval, sucesso dos guardrails. O Claude fez a coisa certa dado o
contexto disponível — e adicionou valor operacional ao identificar o conflito de versões e
recomendar especificamente a v2.

---

## Teste 4 — "Quais são os multiplicadores regionais para frete especial?"

### Chunks Recuperados

| Rank | Fonte | Seção | Score | Relevante? |
|------|-------|-------|-------|------------|
| 1 | anexo-a-documentacao-simulada-novatech.md | 2. Fórmula de cálculo | 0.1596 | ✅ Sim (v. atualizada nov/2023) |
| 2 | anexo-a-documentacao-simulada-novatech.md | 2. Fórmula de cálculo | 0.0998 | ✅ Sim (v. anterior s/ data) |
| 3 | PROC-042-v2-frete-especial-revisado.md | 2. Fórmula de cálculo | 0.0642 | ⚠️ Parcial |
| 4 | PROC-042-frete-especial-v1.md | 2. Fórmula de cálculo | 0.0641 | ⚠️ Parcial |
| 5 | POL-001-politica-devolucao.md | 3.4. Devoluções parciais | -0.0057 | ❌ Não |

**Avaliação dos scores:** Extremamente baixos (máximo 0.1596). O Chunk 5 tem score
**negativo** (-0.0057), indicando dissimilaridade semântica — foi incluído no resultado
apesar de ser semanticamente oposto à query. Um limiar mínimo de corte por score deveria
excluir este chunk automaticamente.

**Análise de relevância chunk a chunk:**

- **Chunk 1 (anexo-a, versão atualizada nov/2023):** Contém a tabela de multiplicadores
  com data de atualização — Norte = **1,8**. Chunk correto, versão vigente.

- **Chunk 2 (anexo-a, versão anterior s/ data):** Contém tabela de multiplicadores sem data
  — Norte = **1,6**. Versão desatualizada com valores diferentes. **Conflito direto com Chunk 1.**

- **Chunks 3 e 4 (PROC-042-v2 e v1):** Contêm a estrutura da fórmula (valor base × multiplicador
  regional × fator de peso), mas os fatores de peso diferem entre v1 (1.2/1.5) e v2 (1.15/1.4).
  Os multiplicadores regionais estão referenciados como "seção 2.1" mas não listados no chunk.

- **Chunk 5 (POL-001, seção 3.4 — Devoluções parciais):** Score negativo. Completamente
  irrelevante — trata de reembolso por volume devolvido. Deveria ter sido excluído por
  limiar mínimo de score.

**⚠️ Comparação com Anexo B:** O chunk correto e vigente é PROC-042-v2 seção 2.1 com
multiplicadores de novembro/2023. A presença de PROC-042-v1 com valores desatualizados
representa risco operacional concreto — um atendente cotando frete Norte usaria 1,6 em vez
de 1,8, gerando subcobrança de receita.

### Avaliação da Resposta do Claude

| Critério | Resultado | Detalhe |
|----------|-----------|---------|
| Resposta factualmente correta? | ✅ | Apresentou ambas as versões sem escolher arbitrariamente |
| Identificou o conflito? | ✅ | Sinalizou explicitamente "Versão A" (nov/2023) e "Versão B" (anterior) |
| Guardrail 2 — não inventar? | ✅ | Não resolveu o conflito por inferência |
| Guardrail 3 — escalar? | ✅ | Recomendou verificar tabela oficial antes de cotar |
| Expôs risco operacional? | ✅ | Alertou que não deve usar valores sem confirmação |

**Veredicto:** O Claude performou bem diante de um conflito real. O problema é estrutural
no pipeline: documentos obsoletos nunca deveriam chegar ao LLM como alternativa válida — a
resolução do conflito não deveria ser responsabilidade do modelo de linguagem.

---

## Teste 5 — "O que o cliente precisa fazer para abrir um chamado de devolução?"

### Chunks Recuperados

| Rank | Fonte | Seção | Score | Relevante? |
|------|-------|-------|-------|------------|
| 1 | POL-001-politica-devolucao.md | 3.5. Custos de devolução | 0.2645 | ⚠️ Parcial |
| 2 | POL-001-politica-devolucao.md | 3.3. Procedimento de devolução | 0.1555 | ✅ Sim |
| 3 | anexo-a-documentacao-simulada-novatech.md | 5. Medição e reportes | 0.1483 | ❌ Não |
| 4 | anexo-a-documentacao-simulada-novatech.md | Documento 4: SLA-2024 | 0.1291 | ❌ Não |
| 5 | SLA-2024-tabela-sla-clientes.md | SLA-2024 — Tabela de SLA | 0.1291 | ❌ Não |

**Avaliação dos scores:** Baixos (máximo 0.2645). Três de cinco chunks são completamente
irrelevantes — 60% do contexto enviado ao LLM é ruído.

**Análise de relevância chunk a chunk:**

- **Chunk 1 (POL-001, 3.5 — Custos):** Sobre responsabilidade de custo e prazo de
  elegibilidade (7 dias úteis). Útil como contexto complementar, mas não responde
  "o que o cliente precisa fazer" — a seção principal seria a 3.3.

- **Chunk 2 (POL-001, 3.3 — Procedimento):** Chunk correto — contém o passo a passo
  completo (portal, CT-e, fotos, triagem). Está no **rank 2**, não no rank 1.

- **Chunks 3, 4 e 5 (SLA-2024 e medição):** Completamente irrelevantes. Sobre medição de
  tempo de SLA e cabeçalho do documento contratual de SLA. Causa: a palavra "chamado" é
  semanticamente comum a ambos os domínios (SLA e devoluções), levando o retriever ao
  domínio errado.

**⚠️ Comparação com Anexo B:** O chunk correto esperado é POL-001 seção 3.3. Está presente
no rank 2, não no 1. Verificar no gabarito se só POL-001 3.3 era esperado ou se 3.5 também
estava listado.

### Avaliação da Resposta do Claude

| Critério | Resultado | Detalhe |
|----------|-----------|---------|
| Resposta factualmente correta? | ✅ | Usou o chunk correto (3.3) apesar de ser rank 2 |
| Citou fontes? | ✅ | POL-001 seções 3.3 e 3.5 com tabela de atribuição |
| Aproveitou chunk parcialmente relevante? | ✅ | Usou 3.5 para informar prazo de elegibilidade |
| Guardrail 3 — sinalizar lacuna? | ✅ | Alertou sobre ausência de instrução para quem não tem acesso ao portal |
| Guardrail 4 — português formal? | ✅ | |

**Veredicto:** Apesar de 60% de ruído no contexto, o Claude construiu uma resposta completa
e correta aproveitando os 2 chunks relevantes. Mostra resiliência dos guardrails — mas o
sistema depende da sorte de o chunk correto estar dentro do top-5. Se o retriever tivesse
retornado um 6º chunk irrelevante no lugar do rank 5, a resposta ainda seria correta. Se
tivesse falhado no rank 2, a resposta seria incompleta.

---

## Quadro Consolidado dos 5 Testes

| # | Pergunta | Score máx | Chunks corretos | Resposta Claude | Resultado geral |
|---|----------|-----------|-----------------|-----------------|-----------------|
| 1 | Prazo devolução não perigosas | 0.2397 | 1/5 | ✅ Escalonamento correto | ⚠️ Falha de retrieval |
| 2 | SLA Gold | 0.3480 | 4/5 | ✅ Resposta completa e precisa | ✅ Sucesso |
| 3 | Cálculo frete 600kg Norte | 0.3495 | 0/5 | ✅ Escalonamento correto | ❌ Falha de retrieval |
| 4 | Multiplicadores regionais | 0.1596 | 2/5* | ✅ Conflito sinalizado | ⚠️ Conflito de versões |
| 5 | Abrir chamado devolução | 0.2645 | 2/5 | ✅ Resposta correta | ⚠️ 60% de ruído no contexto |

*Teste 4: chunks com dados corretos presentes, mas com conflito direto entre versão atual e desatualizada.

**Conclusão geral:** O sistema de guardrails é sólido — em nenhum dos 5 testes o Claude
inventou dados ou violou as regras. O gargalo é o retrieval: apenas 1 de 5 testes teve
retrieval de alta qualidade (Teste 2). Os outros 4 dependeram dos guardrails para degradar
graciosamente. Em produção, um sistema que só funciona bem em 20% das queries tem impacto
direto na redução de tempo de atendimento prometida pela NovaTech (de 12 para menos de 2
minutos por chamado).
