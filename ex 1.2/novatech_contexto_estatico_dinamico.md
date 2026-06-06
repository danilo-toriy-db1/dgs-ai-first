# Documento 2 — Mapeamento de Contexto: Estático vs. Dinâmico

> **Escopo:** Este documento mapeia todos os componentes que ocupam a janela de contexto do
> GPT-4o (128.000 tokens) em cada chamada do Assistente Operacional NovaTech, identifica o
> que é estático vs. dinâmico, e define a política de truncagem quando o orçamento for
> excedido. As estimativas de tokens usam a regra 1 token ≈ 0,75 palavras (≈ 1,33 tok/palavra).

---

## 1. Tabela de Componentes do Contexto

| # | Componente | Posição na chamada | Tipo | Palavras estimadas | Tokens estimados | Frequência de mudança |
|---|---|---|---|---|---|---|
| 1 | Identidade e papel | `system` | **Estático** | ~120 | ~160 | Raramente (versões do prompt) |
| 2 | Instruções de uso dos chunks + hierarquia de fontes | `system` | **Estático** | ~280 | ~375 | Raramente |
| 3 | Guardrails 1–4 | `system` | **Estático** | ~310 | ~415 | Raramente |
| 4 | Formato de resposta | `system` | **Estático** | ~160 | ~215 | Raramente |
| 5 | Tratamento de casos especiais | `system` | **Estático** | ~210 | ~280 | Raramente |
| 6 | Metadados do atendente (nome, fila, nível de acesso) | `system` (injetado) | **Semi-estático** | ~30 | ~40 | Por sessão (~30 min) |
| 7 | Data e turno atual | `system` (injetado) | **Semi-estático** | ~15 | ~20 | Por chamada |
| 8 | Chunks recuperados (documentação interna) | `user` (injetado) | **Dinâmico** | 375–3.750 | 500–5.000 | Por query |
| 9 | Dados contextuais do cliente/pedido | `user` (injetado) | **Dinâmico** | ~75–225 | ~100–300 | Por query |
| 10 | Pergunta do atendente | `user` | **Dinâmico** | ~15–75 | ~20–100 | Por query |
| 11 | Histórico de conversa (turns anteriores) | `assistant` + `user` | **Dinâmico** | 375–3.000 | 500–4.000 | Acumulativo |
| 12 | Espaço reservado para a resposta do modelo | — | **Reserva** | ~375–750 | ~500–1.000 | Por query |

---

## 2. Detalhamento por Tipo

### 2.1 Componentes Estáticos

São os componentes presentes em **100% das chamadas** e raramente alterados. Mudam apenas
quando há uma nova versão do system prompt — evento que ocorre no máximo algumas vezes por
trimestre e exige revisão e validação pelo time de prompt engineering.

**Subtotal estático (componentes 1–5):** ~1.080 palavras → **~1.445 tokens**

```
Identidade e papel:                     ~160 tokens
Instruções de chunks + hierarquia:      ~375 tokens
Guardrails 1–4:                         ~415 tokens
Formato de resposta:                    ~215 tokens
Casos especiais:                        ~280 tokens
─────────────────────────────────────────────────
TOTAL ESTÁTICO:                       ~1.445 tokens
```

**Implicação de design:** por serem fixos, esses componentes são o candidato natural para
compressão se o orçamento ficar apertado. Porém, compressão de guardrails é arriscada —
linguagem ambígua em regras de comportamento produz falhas silenciosas que só aparecem em
casos de borda. Prefira otimizar os componentes dinâmicos antes de tocar os estáticos.

---

### 2.2 Componentes Semi-estáticos

Mudam em frequência intermediária — por sessão ou por chamada, mas com conteúdo previsível
e de baixo volume. São injetados programaticamente no campo `system` logo após o prompt base.

**Metadados do atendente (componente 6):**
```
Nome: Ana Rodrigues
Fila: Atendimento Corporativo — Contas Nível 2
Nível de acesso à documentação: Padrão (sem acesso a RN- confidenciais)
Turno: Tarde
```
→ ~40 tokens. Presente em toda chamada da sessão; muda quando o atendente troca de fila
ou faz login em outra sessão.

**Data e turno (componente 7):**
```
Data atual: 2025-06-05 | Turno: 14h–22h
```
→ ~20 tokens. Relevante para queries sobre prazos ("até quando posso protocolar hoje?").

**Subtotal semi-estático (componentes 6–7):** **~60 tokens**

---

### 2.3 Componentes Dinâmicos

São os componentes que mudam a cada query e consomem a maior parte do orçamento variável.

#### Componente 8 — Chunks recuperados

O volume de chunks é a principal variável de custo e qualidade do sistema. O intervalo é
amplo porque o número de chunks (`k`) é ajustado dinamicamente por tipo de query (conforme
a Análise Técnica v2, seção 3).

| Tipo de query | k (chunks) | Tokens por chunk | Tokens totais (chunks) |
|---|---|---|---|
| Factual simples | 3–5 | ~500 | 1.500–2.500 |
| Operacional | 5–10 | ~500 | 2.500–5.000 |
| Analítica / síntese | 10–20 | ~500 | 5.000–10.000 |

Em produção, usar **k = 8 como padrão** (4.000 tokens) com ajuste dinâmico para cima em
queries analíticas e para baixo em queries factuais com alta confiança no retriever.

Os chunks são injetados no turno `user`, antes da pergunta, no seguinte formato:

```
[DOCUMENTAÇÃO RECUPERADA]

--- CHUNK 1 de 8 ---
Fonte: POL-032 | Seção: 3.1 | Score de relevância: 0.94
Data de revisão: 2024-11-15
"O prazo padrão para coleta domiciliar é de 2 (dois) dias úteis contados
a partir da confirmação eletrônica do pedido pelo sistema TMS..."

--- CHUNK 2 de 8 ---
Fonte: POP-047 | Seção: 2.3 | Score de relevância: 0.87
...

[FIM DA DOCUMENTAÇÃO RECUPERADA]
```

O score de relevância é incluído propositalmente no prompt: pesquisas mostram que modelos
tendem a calibrar sua confiança na resposta quando informados da qualidade do retrieval.
Chunks com score abaixo de 0,60 devem ser omitidos ou marcados com aviso de baixa
relevância para evitar que o modelo construa respostas sobre evidência fraca.

#### Componente 9 — Dados contextuais do cliente/pedido

Informações extraídas do CRM ou TMS da NovaTech e injetadas automaticamente quando
disponíveis. Exemplos:

```
[CONTEXTO DO ATENDIMENTO]
Cliente: Distribuidora Alfa Ltda. | Contrato: CNT-2891 | Segmento: Varejo B2B
Pedido em foco: PED-774201 | Status: Em trânsito | Origem: Recife/PE | Destino: Fortaleza/CE
SLA contratual: 3 dias úteis | Prazo comprometido: 2025-06-07
Ocorrências abertas: nenhuma
[FIM DO CONTEXTO]
```

→ ~100–300 tokens. Crítico para queries de exceção ("o cliente diz que o prazo não foi
cumprido") pois ancora o modelo na situação específica em vez de responder em abstrato.

#### Componente 10 — Pergunta do atendente

→ 20–100 tokens. Geralmente concisa. Não há ação de otimização necessária aqui.

#### Componente 11 — Histórico de conversa

É o componente com crescimento mais perigoso: cada turno adiciona 200–800 tokens ao
contexto acumulado. Uma conversa de 8 turnos pode consumir 3.000–6.000 tokens só de
histórico.

Estratégia de gestão: manter os **3 turnos mais recentes completos** e substituir os
anteriores por um **resumo comprimido** (gerado pelo modelo no final de cada turno com
instrução de sistema separada). O resumo de 5+ turnos anteriores deve ter no máximo
200–300 tokens.

```
[RESUMO DA CONVERSA ATÉ AGORA]
Atendente consultou sobre prazo de coleta (POL-032: 2 dias úteis confirmados).
Em seguida perguntou sobre cobertura de seguro para carga frágil (chunks
insuficientes — escalonamento recomendado para Coordenação Comercial).
[FIM DO RESUMO]

[HISTÓRICO RECENTE — últimos 3 turnos]
...
```

---

## 3. Orçamento Total e Margens

### Cenário Base (query operacional, k=8)

```
Componentes estáticos (1–5):         1.445 tokens
Semi-estáticos (6–7):                   60 tokens
Chunks recuperados (k=8 × 500):      4.000 tokens
Dados do cliente (componente 9):       200 tokens
Pergunta do atendente (comp. 10):       60 tokens
Histórico — resumo + 3 turnos (11):    800 tokens
Reserva para resposta do modelo:       700 tokens
──────────────────────────────────────────────────
TOTAL UTILIZADO:                     7.265 tokens
MARGEM DISPONÍVEL:                 120.735 tokens  (94,3% livre)
```

**Conclusão do cenário base:** o sistema está bem dentro do orçamento na operação normal.
A janela de 128k é ampla o suficiente para acomodar até mesmo cenários analíticos pesados
sem risco de truncagem.

### Cenário Extremo (query analítica, k=20, histórico longo)

```
Componentes estáticos (1–5):         1.445 tokens
Semi-estáticos (6–7):                   60 tokens
Chunks recuperados (k=20 × 500):    10.000 tokens
Dados do cliente (componente 9):       300 tokens
Pergunta do atendente (comp. 10):      100 tokens
Histórico — resumo + 3 turnos (11):  2.500 tokens
Reserva para resposta do modelo:     1.000 tokens
──────────────────────────────────────────────────
TOTAL UTILIZADO:                    15.405 tokens
MARGEM DISPONÍVEL:                 112.595 tokens  (87,9% livre)
```

**Conclusão:** mesmo no cenário extremo, o sistema consome apenas ~12% da janela disponível.
O limite de 128k não é uma ameaça real para este caso de uso com os parâmetros definidos.
O risco de orçamento é **econômico, não técnico**: cada token de input tem custo, e
otimizar o número de chunks impacta diretamente o custo por query.

---

## 4. Política de Truncagem (quando o orçamento for excedido)

Embora o cenário base esteja bem dentro do limite, a política abaixo deve ser implementada
como salvaguarda — especialmente para versões futuras do sistema com chunking mais agressivo,
modelos de janela menor, ou conversas excepcionalmente longas.

O gatilho de truncagem é acionado quando o contexto projetado ultrapassar **100.000 tokens**
(78% da janela), reservando 28.000 tokens como margem de segurança.

### Ordem de truncagem (do menos crítico para o mais crítico)

Aplicar na sequência abaixo, verificando após cada etapa se o orçamento foi recuperado:

**Passo 1 — Comprimir o histórico de conversa**
Substituir todos os turnos exceto os 2 mais recentes por um resumo ainda mais comprimido
(máximo 150 tokens). Economia esperada: 500–2.000 tokens.

**Passo 2 — Reduzir o número de chunks**
Diminuir `k` progressivamente: 20 → 15 → 10 → 8 → 5. Nunca ir abaixo de 3 chunks —
abaixo disso, o risco de resposta sem embasamento supera o benefício da truncagem.
Ao truncar chunks, remover pelos **menores scores de relevância** primeiro, nunca por
posição no prompt. Economia por chunk removido: ~500 tokens.

**Passo 3 — Remover dados contextuais do cliente**
O componente 9 (dados do CRM/TMS) é valioso mas dispensável se o atendente puder fornecer
o contexto verbalmente na pergunta. Economia: 100–300 tokens.

**Passo 4 — Comprimir o system prompt (último recurso)**
Substituir o system prompt completo por uma versão comprimida pré-gerada (~600 tokens)
que mantém os 4 guardrails e a hierarquia de fontes, mas remove exemplos, justificativas
e detalhamento de casos especiais. Esta versão comprimida deve ser preparada e validada
antecipadamente — não gerada on-the-fly em runtime.

**O que nunca deve ser truncado:**
- Os guardrails 1–4 (qualquer versão do prompt)
- A hierarquia de prioridade entre fontes
- O chunk com maior score de relevância (posição 1 no contexto)

### Alerta ao atendente

Quando a truncagem for acionada, o sistema deve incluir uma nota visível na interface
do atendente (não na resposta do modelo):

```
⚠ AVISO: O histórico desta conversa foi comprimido para otimizar o contexto.
Informações de turnos anteriores podem não estar completamente disponíveis
para esta resposta. Se necessário, reinicie a consulta com o contexto
completo.
```

---

## 5. Diagrama de Montagem do Contexto por Chamada

```
┌─────────────────────────────────────────────────────────┐
│                    CHAMADA À API                         │
├─────────────────────────────────────────────────────────┤
│  POSIÇÃO: system                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  [ESTÁTICO]  System Prompt Base         ~1.445 tok│   │
│  │  [SEMI]      Metadados do atendente        ~40 tok│   │
│  │  [SEMI]      Data e turno atual            ~20 tok│   │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  POSIÇÃO: user (turno atual)                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │  [DINÂMICO]  Contexto do cliente/pedido   ~200 tok│   │
│  │  [DINÂMICO]  Chunks recuperados (k × 500tok)     │   │
│  │              Chunk 1 (score mais alto)           │   │
│  │              Chunks 2..k-1 (relevância média)    │   │
│  │              Chunk k (score 2º mais alto)         │   │
│  │              ← ordenação anti-lost-in-middle      │   │
│  │  [DINÂMICO]  Pergunta do atendente         ~60 tok│   │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  POSIÇÃO: assistant + user (turns anteriores)           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  [DINÂMICO]  Resumo comprimido (turns antigos)   │   │
│  │  [DINÂMICO]  Últimos 3 turns completos           │   │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│  RESERVA: resposta do modelo                    ~700 tok │
└─────────────────────────────────────────────────────────┘
```

**Nota sobre a ordenação dos chunks:** os chunks são posicionados no contexto seguindo a
estratégia anti-*lost in the middle* descrita na Análise Técnica v2: chunk de maior score
no início, chunks intermediários no meio, chunk de segundo maior score ao final. Essa
ordenação é responsabilidade da camada de orquestração (não do modelo), e deve ser aplicada
antes da injeção no prompt.

---

## 6. Recomendações para Evolução do Sistema

**Monitorar o custo por query desde o dia 1.** Com `k=8` e chunks de 500 tokens, cada
query consome ~7.000 tokens de input + ~700 tokens de output. Com GPT-4o (Jun/2025),
isso representa aproximadamente US$ 0,04–0,07 por query. Em escala de 500 queries/dia,
o custo mensal de geração é manejável (~US$ 600–1.000/mês), mas aumenta linearmente com
`k` e com o número de usuários.

**Introduzir cache semântico progressivamente.** Queries semanticamente idênticas ou muito
próximas (threshold de similaridade > 0,95 nos embeddings da query) podem retornar resposta
cacheada sem chamar o modelo. Em contextos corporativos, 20–35% das queries são repetições
de perguntas frequentes — o cache reduz tanto custo quanto latência.

**Versionar o system prompt como código.** O system prompt é um artefato de engenharia, não
um documento de texto. Deve estar em controle de versão (Git), ter testes automatizados
de comportamento (um conjunto de queries de regressão que verifica se os guardrails
continuam sendo respeitados após cada edição), e ter um processo de aprovação antes de
ir a produção.

**Planejar a versão comprimida do prompt agora.** A versão de fallback (~600 tokens) descrita
no Passo 4 da política de truncagem não deve ser escrita às pressas quando o problema
acontecer. Deve ser preparada, testada e mantida em paralelo com o prompt completo.

---

*Documento produzido para uso interno — Squad RAG NovaTech | Jun/2025*
*Referência cruzada: Análise Técnica RAG NovaTech v2.0*
