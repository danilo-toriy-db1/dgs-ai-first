# Análise Técnica — Viabilidade do Assistente RAG NovaTech
### Versão 2.0 — Revisão Crítica Incorporada

---

> **Nota de escopo:** Esta análise cobre a viabilidade técnica do pipeline RAG, com ênfase em
> ingestão, chunking e retrieval. Decisões de infraestrutura (hospedagem, escolha de banco
> vetorial, modelo de embedding) são mencionadas onde impactam diretamente as recomendações,
> mas não são o foco principal. Uma fase de prova de conceito de 4–6 semanas é fortemente
> recomendada antes de qualquer decisão de arquitetura final.

---

## 1. Desafios por Tipo de Fonte

### 1.1 PDFs com Tabelas Complexas (15+ colunas)

**Desafio principal**

A maioria dos parsers de PDF (PyMuPDF, pdfplumber, PDFMiner) serializa tabelas em texto
linear — percorrendo célula por célula, linha por linha. Com 15 ou mais colunas, esse processo
produz sequências de texto sem qualquer estrutura relacional legível. Cabeçalhos multi-nível
(células mescladas abrangendo várias colunas) são frequentemente descartados ou duplicados de
forma incorreta. O resultado é um chunk que parece ruído para o modelo, sem preservar o
relacionamento entre coluna e valor.

Um problema adicional, não trivial, é que documentos corporativos raramente têm distribuição
uniforme de conteúdo. É comum que 20% dos PDFs do SharePoint tenham mais de 50 páginas
(contratos, manuais técnicos, relatórios anuais) enquanto 40% têm menos de 3 páginas (atas
curtas, emails convertidos). Isso significa que o pipeline de extração precisa ser robusto a
essa heterogeneidade — um documento de 200 páginas com múltiplas tabelas exige tratamento
diferente de dez documentos de 20 páginas.

**Impacto na qualidade das respostas**

Perguntas do tipo "Qual é o prazo de entrega para o fornecedor X na categoria Y?" dependem de
coordenadas de linha e coluna para ser respondidas. Com a estrutura destruída, o modelo ou
inventa uma resposta plausível (alucinação estrutural) ou afirma não ter encontrado a
informação, mesmo que ela esteja presente no corpus.

**Estratégia de tratamento recomendada**

Usar uma pipeline de extração em dois estágios. Primeiro, detectar tabelas com biblioteca
especializada: Camelot (modo lattice para tabelas com bordas explícitas) ou pdfplumber com
detecção de bounding boxes. Segundo, converter cada tabela para Markdown de forma programática,
preservando os cabeçalhos.

Para o contexto narrativo que circunda tabelas — parágrafos do tipo "conforme demonstrado na
tabela abaixo, os valores de..." — é necessário criar um chunk de transição que inclua os dois
ou três parágrafos imediatamente anteriores à tabela seguidos pelo cabeçalho dela. Isso evita
que o contexto explicativo se perca: sem essa junção, o chunk narrativo não tem os dados e o
chunk de tabela não tem a interpretação.

Para tabelas grandes demais para caber em um único chunk (acima de 1.000 tokens), particionar
por grupo de linhas mantendo os cabeçalhos **repetidos** em cada partição. Complementar com um
índice estruturado separado — indexar as tabelas como documentos JSON no banco vetorial com
metadados de coluna — permitindo retrieval híbrido: busca semântica para localizar a tabela
certa, busca estruturada para extrair o valor exato.

---

### 1.2 PDFs com Fluxogramas e Imagens Embutidas

**Desafio principal**

O brief menciona explicitamente fluxogramas embutidos como imagens nos PDFs. Este é um problema
distinto dos PDFs escaneados: o documento é textual e extraível, mas contém imagens internas
que encapsulam informação de processo crítica — sequências de aprovação, árvores de decisão,
diagramas de fluxo operacional. Esses elementos são completamente invisíveis para qualquer
parser de texto convencional.

**Impacto na qualidade das respostas**

O processo descrito em um fluxograma frequentemente é o conteúdo mais importante de um
documento de política ou procedimento. Se o fluxograma descreve as etapas de aprovação de um
pedido e o texto narrativo apenas o referencia ("veja o diagrama ao lado"), o chunk extraído
terá a referência mas não o conteúdo — produzindo respostas incompletas exatamente nas queries
operacionais mais frequentes.

**Estratégia de tratamento recomendada**

Aplicar um modelo de visão (Vision LLM) sobre as imagens extraídas dos PDFs durante a
ingestão. O processo é: extrair todas as imagens embutidas com PyMuPDF (`page.get_images()`);
filtrar imagens com dimensões abaixo de 100×100 pixels (ícones decorativos); enviar as imagens
remanescentes para um modelo multimodal (GPT-4o Vision ou Claude com capacidade de visão) com
um prompt estruturado pedindo a descrição do fluxograma em linguagem natural, incluindo todos
os nós, decisões e setas do processo. O texto gerado é então indexado como um chunk separado,
com metadados indicando que é uma descrição de imagem gerada por IA (para fins de auditoria e
filtragem opcional).

Essa abordagem tem custo adicional por token de imagem, portanto deve ser aplicada seletivamente:
priorizar PDFs de procedimentos e políticas operacionais, onde fluxogramas são mais prováveis.

---

### 1.3 PDFs Escaneados (OCR Necessário)

**Desafio principal**

Documentos escaneados não contêm texto extraível — são imagens de páginas. O OCR introduz
erros que variam conforme a qualidade da digitalização: caracteres confundidos (0/O, 1/l/I),
palavras segmentadas incorretamente e perda de formatação. Um risco crítico e frequentemente
subestimado é a confiabilidade dos scores de confiança do próprio OCR: o Tesseract avalia
confiança por caractere, não por coerência semântica. Um score de 91% pode mascarar um
parágrafo inteiro ilegível se os erros forem em palavras-chave de baixa frequência (nomes
próprios, siglas internas, valores numéricos). O número-limiar de 85% usado em projetos
anteriores é um ponto de partida, não uma garantia — precisa ser calibrado contra uma amostra
real dos documentos da NovaTech.

**Impacto na qualidade das respostas**

Um chunk com texto corrompido gera embeddings que não correspondem às queries do usuário — o
documento existe no corpus mas nunca é recuperado, criando pontos cegos invisíveis. Pior: quando
recuperado por coincidência, o modelo recebe texto fragmentado e pode produzir respostas
parcialmente erradas sem sinalizar incerteza.

**Estratégia de tratamento recomendada**

Aplicar OCR com Tesseract 5 (modo LSTM) ou, preferencialmente, Azure Document Intelligence /
Google Document AI para documentos críticos, pois esses serviços têm precisão superior em
layouts complexos e retornam bounding boxes por palavra (úteis para reconstrução de tabelas).

Antes do OCR, pré-processar as imagens: binarização adaptativa, correção de inclinação
(deskewing) e aumento de resolução para no mínimo 300 DPI. Após o OCR, executar pós-correção
com spell-checking contextual para corrigir erros sistemáticos.

O score de confiança do OCR deve ser armazenado como metadado do chunk. Mas, em vez de um
único limiar binário, usar três faixas:

- **≥ 90%:** ingestão automática.
- **75–89%:** ingestão com flag de baixa confiança, incluída nos metadados retornados ao
  usuário na resposta ("esta informação vem de um documento com qualidade de OCR reduzida").
- **< 75%:** bloqueado para revisão humana antes de entrar em produção.

Esse modelo de três faixas é mais robusto que um limiar binário e evita tanto a exclusão
excessiva de documentos recuperáveis quanto a ingestão silenciosa de texto ilegível.

---

### 1.4 Wiki do Confluence (Links Internos e Macros)

**Desafio principal**

O Confluence exporta páginas em HTML ou via API REST. O HTML exportado contém macros
renderizadas como elementos DOM opacos cujo conteúdo textual relevante é perdido ou
transformado em texto sem contexto. Links internos entre páginas criam dependências de conteúdo
que o chunking por página destrói.

O problema do grafo de dependências é mais complexo do que parece inicialmente. O Confluence
tem links circulares (página A referencia B, que referencia A), páginas órfãs sem ligação ao
restante da hierarquia, e páginas que referenciam conteúdo em espaços diferentes ou
completamente externos. Para lidar com isso, é necessário definir regras explícitas:

- **Profundidade de expansão:** agregar apenas 1 nível de filhos diretos por padrão; não
  expandir recursivamente, pois uma página-pai com 40 filhas produziria um "documento lógico"
  ingerível de dezenas de milhares de tokens.
- **Ciclos:** detectar e quebrar ciclos no grafo mantendo apenas a aresta na direção da
  hierarquia principal (pai → filho); referências laterais entre irmãos são tratadas como
  metadados de relacionamento, não como fusão de conteúdo.
- **Páginas órfãs:** indexar individualmente com metadado `is_orphan: true` para posterior
  revisão pelo time de conteúdo.

**Impacto na qualidade das respostas**

Perguntas que dependem de informações distribuídas em múltiplas páginas interligadas —
"Qual é o processo completo de onboarding de um novo fornecedor?" — retornam respostas
incompletas se a página principal é recuperada mas as subpáginas referenciadas não. Macros
como Jira Issues ou Table of Contents que listam itens dinamicamente ficam completamente
vazias no texto extraído.

**Estratégia de tratamento recomendada**

Usar a API REST do Confluence (não a exportação em lote) para extração. A API retorna o corpo
da página em storage format (XML/XHTML), permitindo parsear macros conhecidas por nome e
extrair seu conteúdo de forma semântica. Manter um mapa de macros conhecido: para cada tipo de
macro relevante (Panel, Info, Warning, Decision, Status), definir uma função de serialização
que extraia o conteúdo textual com contexto adequado.

Labels e metadados do Confluence (espaço, hierarquia de ancestrais, data de modificação,
etiquetas, autor) devem ser indexados como metadados filtráveis, permitindo retrieval por
espaço ou tipo de documento.

---

### 1.5 Planilhas Excel com Fórmulas Interdependentes

**Desafio principal**

Fórmulas como `=VLOOKUP(A2,Budget!$A:$D,3,0)` não têm valor informativo isoladas. Mesmo que
o parser execute as fórmulas e extraia os valores calculados, o contexto semântico é perdido:
o número "142.500" sem saber que é a "meta de vendas do Q3 para a região Sul" é inútil para
o modelo.

Um risco adicional é a escala dentro dos arquivos. A estimativa conservadora de 800
palavras por planilha pode subestimar em 3–5x os arquivos mais densos: planilhas de orçamento
corporativo frequentemente têm dezenas de abas, milhares de linhas, comentários de célula
extensos e histórico de versões embutido. O pipeline precisa lidar com planilhas de 10.000+
linhas sem travar ou gerar chunks incoerentes.

Existe também uma tensão fundamental no perfil de uso: uma planilha de orçamento pode ser
consultada tanto fatualmente ("qual é o valor do contrato X?") quanto analiticamente ("como o
Q3 se compara ao planejado?"). O chunking ideal para cada tipo de pergunta é diferente, e não
é possível saber durante a ingestão qual tipo de pergunta o usuário fará. Isso exige uma
estratégia de indexação dupla, descrita abaixo.

**Impacto na qualidade das respostas**

Perguntas analíticas como "Qual região está abaixo da meta neste trimestre?" requerem que o
modelo entenda a relação entre células, abas e valores calculados. Sem esse contexto, o modelo
ou não responde ou responde com base apenas nos valores recuperados, sem compreender o que eles
representam.

**Estratégia de tratamento recomendada**

Usar openpyxl para ler planilhas com valores calculados (não as fórmulas em si). Para cada
aba, serializar os dados como tabela Markdown com cabeçalhos explícitos. Incluir no início de
cada chunk uma descrição gerada automaticamente: nome do arquivo, nome da aba, propósito
inferido dos cabeçalhos, intervalo de datas se detectável, e lista de abas das quais esta
recebe dados (dependências de fórmulas extraídas estaticamente).

Para endereçar a tensão factual vs. analítica, implementar indexação em dois formatos
paralelos para planilhas estruturadas (orçamento, metas, KPIs):

**Formato 1 — chunks tabulares** (para queries factuais): cada bloco de linhas da aba, com
cabeçalhos repetidos, tamanho alvo de 600–800 tokens.

**Formato 2 — sumário executivo em linguagem natural** (para queries analíticas): um chunk
por aba descrevendo em prosa os valores-chave, totais, variações percentuais e comparações
entre colunas relevantes. Gerado uma vez durante a ingestão com um LLM e indexado junto
com os chunks tabulares.

---

## 2. Estimativa da Base em Tokens

### Cálculos por Fonte

**PDFs**

```
800 documentos × 10 páginas/doc (média) = 8.000 páginas
8.000 páginas × 250 palavras/página = 2.000.000 palavras
2.000.000 × 1,33 tokens/palavra = 2.660.000 tokens
```

*Ressalva importante:* a média de 10 páginas oculta uma distribuição com cauda longa. Estimando
que 15% dos documentos têm mais de 40 páginas e 35% têm menos de 3 páginas, o volume real pode
variar entre 2,2M e 3,8M tokens dependendo do conteúdo efetivo. A cifra de 2,66M deve ser
tratada como estimativa central, não como limite superior.

**Wiki do Confluence**

```
400 páginas × 1.500 palavras/página (média) = 600.000 palavras
600.000 × 1,33 = 798.000 tokens
```

*Ressalva:* páginas wiki corporativas têm alta variância — de 200 palavras (páginas de
referência rápida) a 8.000+ (especificações técnicas). Além disso, conteúdo duplicado entre
páginas (copiar-colar de seções de política entre departamentos) é comum e pode representar
15–25% do volume bruto sem deduplicação.

**Planilhas Excel**

Estimativa revisada: 800 palavras por arquivo é conservador. Usando uma distribuição mais
realista — 40% dos arquivos com menos de 500 palavras (planilhas simples de acompanhamento),
40% com 800–2.000 palavras (relatórios mensais), 20% com 3.000–6.000 palavras (orçamentos
anuais completos):

```
20 arquivos × 400 palavras = 8.000 palavras
20 arquivos × 1.400 palavras = 28.000 palavras
10 arquivos × 4.500 palavras = 45.000 palavras
Total: 81.000 palavras × 1,33 = 107.730 tokens
```

### Consolidado com Intervalos de Incerteza

| Fonte           | Estimativa central | Intervalo realista    |
|-----------------|--------------------|-----------------------|
| PDFs            | 2.660.000 tokens   | 2.200.000–3.800.000   |
| Confluence      | 798.000 tokens     | 600.000–1.100.000     |
| Planilhas Excel | 107.730 tokens     | 70.000–200.000        |
| **Total**       | **~3.570.000**     | **~2.870.000–5.100.000** |

**A base tem aproximadamente 3,5 milhões de tokens na estimativa central, podendo chegar a
5 milhões em cenário pessimista.** Para referência: isso equivale a 27–40 janelas completas
do GPT-4o. O RAG é a arquitetura obrigatória, não opcional.

**Atenção à deduplicação:** antes de dimensionar o índice vetorial, executar deduplicação com
MinHash LSH ou embeddings de similaridade entre documentos. É razoável esperar que 15–30% dos
chunks brutos sejam duplicatas ou near-duplicatas em corpora corporativos com documentos que
evoluem ao longo do tempo.

---

## 3. Análise de Orçamento de Contexto

### Distribuição da Janela (128.000 tokens)

| Componente                       | Tokens reservados | Disponível após dedução |
|----------------------------------|-------------------|-------------------------|
| Janela total do GPT-4o           | —                 | 128.000                 |
| System prompt + instruções fixas | 2.000             | 126.000                 |
| Histórico de conversa (média)    | 1.000             | 125.000                 |
| Espaço para a resposta do modelo | 2.000             | 123.000                 |
| **Disponível para chunks**       | —                 | **~123.000**            |

Matematicamente, caberiam ~246 chunks de 500 tokens. Na prática, esse número é inoperável
por três razões:

**Custo:** uma query consumindo 128k tokens de input com GPT-4o custa aproximadamente
US$ 1,60–3,20 por chamada. Em escala corporativa, isso torna o sistema economicamente
inviável sem otimização agressiva.

**Latência:** prompts de 100k+ tokens adicionam 8–15 segundos de tempo de inferência antes
da primeira palavra da resposta — inaceitável para um assistente de produtividade.

**Qualidade:** o efeito *lost in the middle* (detalhado abaixo) degrada a qualidade com
contextos longos independentemente do modelo.

### Número Prático de Chunks por Query

O número ótimo de chunks não é fixo — varia com o tipo de query:

| Tipo de query           | Chunks recomendados | Raciocínio                                                |
|-------------------------|---------------------|-----------------------------------------------------------|
| Factual simples         | 3–5                 | A resposta está em um único local; mais chunks adicionam ruído |
| Operacional             | 5–10                | Pode envolver 2–3 documentos relacionados                 |
| Analítica / síntese     | 10–20               | Requer múltiplas fontes; aceita contexto mais longo        |
| Comparativa             | 8–15                | Par a par entre documentos específicos                    |

A estratégia mais eficaz é classificar a intenção da query antes do retrieval — um
classificador leve (modelo de embeddings com poucas classes) identifica o tipo de pergunta e
ajusta o `k` do retrieval dinamicamente. Usar um valor fixo de 8–15 chunks para todas as
queries é uma simplificação que penaliza especificamente as queries analíticas, que são também
as mais valiosas para o negócio.

### Implicações para a Estratégia de Retrieval

Com um `k` prático de 5–20 chunks e um corpus de ~7.000 chunks totais (3,5M tokens ÷ 500
tokens/chunk), o retriever precisa encontrar os chunks relevantes no top 0,07%–0,3% do corpus
por query. Isso é um requisito de precisão extremamente alto — e explica por que a pipeline
de retrieval precisa de múltiplas camadas:

**Camada 1 — Retrieval semântico (dense retrieval):** busca por embeddings (cosine
similarity) para correspondência de intenção. Retorna top-50 candidatos.

**Camada 2 — Retrieval léxico (BM25):** para termos técnicos, siglas e nomes próprios que
modelos de embedding tendem a normalizar incorretamente. Particularmente importante para
siglas internas da NovaTech ("CCPN", "ROP-07", "Formulário GR-412") cujas representações
vetoriais podem colidir com termos comuns. Retorna top-30 candidatos adicionais.

**Fusão (Reciprocal Rank Fusion):** combinar os resultados das duas camadas sem necessidade
de calibrar scores de diferentes espaços vetoriais.

**Camada 3 — Reranking (cross-encoder):** aplicar um cross-encoder (Cohere Rerank ou
BGE-Reranker) sobre o pool combinado de candidatos para selecionar os `k` finais.

**Atenção ao custo do reranking:** cross-encoders adicionam 500ms–2s de latência por query e
têm custo por token (Cohere Rerank cobra por query sobre o pool de candidatos). Em 50
candidatos com chunks de 500 tokens, isso é 25.000 tokens por query de reranking. O
reranking é justificado — mas deve ser considerado no dimensionamento de custos operacionais,
não tratado como solução gratuita.

**Ponto crítico:** o reranking melhora a precisão dentro do conjunto de candidatos
recuperados, mas não consegue recuperar o que o retriever não trouxe. Se os chunks
relevantes não estiverem nos top-50+30 do retrieval inicial, o reranker não resolve. Isso
torna a qualidade do índice de embeddings e do índice BM25 — e, por extensão, a qualidade
do chunking — o gargalo real de todo o sistema.

### Efeito *Lost in the Middle* — Posicionamento e Mitigação

Pesquisas empíricas (Liu et al., 2023) demonstram que LLMs utilizam mais efetivamente
informações no início e no final do contexto, com degradação sistemática no meio.

**Estratégia de posicionamento no prompt:**

```
[System prompt]
[Chunk mais relevante — score mais alto]     ← Posição de maior atenção
[Chunks de relevância intermediária]         ← Zona de atenção degradada
[Segundo chunk mais relevante]               ← Recupera atenção no final
[Instrução de resposta]
```

**Mitigação estrutural via chunking:** chunks menores e mais precisos reduzem a quantidade
de informação no contexto, diminuindo a probabilidade de conteúdo crítico cair na zona
degradada. Porém, há um conflito direto com a recomendação de chunks maiores para queries
analíticas — esse tradeoff não tem resolução universal e deve ser calibrado empiricamente
na fase de avaliação com as queries reais da NovaTech.

---

## 4. Estratégia de Chunking Recomendada

### Perfil de Queries Esperadas

O usuário típico da NovaTech fará perguntas em três categorias com características distintas:

**Operacionais** ("Como faço para solicitar um equipamento?", "Qual é o prazo para renovação
de contratos?"): requerem chunks pequenos e precisos. A resposta está em uma seção específica
de um único documento.

**Factuais** ("Qual é o CNPJ do fornecedor X?", "Quem é o responsável pelo projeto Y?"):
dependem de recuperação de entidades específicas. Chunks pequenos com contexto suficiente para
identificar a entidade são ideais.

**Analíticas** ("Compare o orçamento previsto vs. realizado do Q2", "Quais projetos estão em
risco de atraso?"): requerem múltiplos chunks de fontes diferentes, com contexto suficiente
para síntese. Chunks maiores reduzem o número de chamadas de retrieval necessárias.

**A tensão entre esses perfis não tem resolução única no chunking.** A estratégia mais robusta
é usar tamanhos diferentes por tipo de fonte — não por tipo de query, pois isso não é
conhecível no momento da ingestão — e compensar com retrieval dinâmico (k variável por
intenção inferida da query).

### Estratégia por Fonte

**PDFs com conteúdo narrativo (políticas, procedimentos):**
Chunking por seção semântica — identificar quebras de seção pelo header hierárquico (H1, H2,
H3) e criar um chunk por seção, com tamanho alvo de 400–600 tokens. Adicionar overlap de
60–80 tokens entre chunks consecutivos. Incluir o título da seção e o título do documento no
início de cada chunk como contexto explícito (não contado no limite de tokens do chunk).

**PDFs com tabelas:**
Chunks de tabela são tratados separadamente do texto narrativo — mas com uma exceção
importante: criar um chunk de transição para cada tabela que inclua os dois ou três parágrafos
imediatamente anteriores mais o cabeçalho da tabela. Isso preserva o contexto interpretativo.
O chunk da tabela em si tem overlap zero (para não duplicar estrutura). Chunks de tabela
incluem obrigatoriamente: título do documento, título da seção, cabeçalhos das colunas
repetidos em todas as partições.

**PDFs escaneados:**
Chunking mais conservador — 300–500 tokens com overlap maior (80–100 tokens) para compensar
possíveis erros de segmentação do OCR. Score de confiança armazenado como metadado.

**Confluence:**
Chunking hierárquico por seção da página (delimitada por cabeçalhos). Páginas curtas (abaixo
de 300 tokens) são agregadas com páginas irmãs na mesma hierarquia. A profundidade de
expansão de links é limitada a 1 nível de filhos diretos para evitar "documentos lógicos"
ingeríveis. Metadados do Confluence (espaço, ancestrais, labels, data de atualização) indexados
como campos filtráveis.

**Planilhas:**
Indexação dupla conforme descrito na seção 1.5 — chunks tabulares (600–800 tokens com
cabeçalhos repetidos) para queries factuais, e sumários executivos em prosa para queries
analíticas, co-indexados com os chunks tabulares da mesma aba.

### Tabela Resumo

| Fonte                    | Tamanho alvo  | Overlap    | Unidade de chunking              | Metadados obrigatórios                                    |
|--------------------------|---------------|------------|----------------------------------|-----------------------------------------------------------|
| PDFs narrativos          | 400–600 tok   | 60–80 tok  | Seção semântica (header)         | Título doc, seção, número da página                       |
| PDFs — tabelas           | até 1.000 tok | 0          | Tabela + chunk de transição      | Título doc, seção, cabeçalhos das colunas                 |
| PDFs — transição tabela  | 200–300 tok   | —          | Parágrafos pré-tabela + cabeçalho| Título doc, seção, referência ao chunk de tabela          |
| PDFs — imagens/fluxogramas| 300–500 tok  | —          | Descrição gerada por Vision LLM  | Título doc, página, tipo: "descrição_imagem_gerada"       |
| PDFs escaneados (OCR)    | 300–500 tok   | 80–100 tok | Bloco de parágrafos              | Score OCR, título doc, flag de confiança                  |
| Confluence               | 300–600 tok   | 50 tok     | Seção da página                  | Espaço, ancestrais, labels, data atualização              |
| Planilhas — tabular      | 600–800 tok   | 0          | Aba por blocos de linhas         | Nome arquivo, nome aba, dependências de fórmulas          |
| Planilhas — sumário      | 400–600 tok   | —          | Prosa por aba (gerada na ingestão)| Nome arquivo, nome aba, tipo: "sumario_executivo"        |

---

## 5. Avaliação e Métricas de Qualidade

Um sistema RAG não tem uma "taxa de acerto" óbvia e auto-evidente. Sem uma estratégia de
avaliação contínua, é impossível saber se o sistema está funcionando bem, se degradou após
uma atualização da base, ou se uma mudança no chunking melhorou ou piorou a qualidade.

### Métricas de Retrieval

**Recall@k:** dos documentos relevantes para uma query, quantos estão nos top-k recuperados?
Esta é a métrica mais crítica — um chunk não recuperado nunca pode ser respondido corretamente.
Alvo mínimo: Recall@10 ≥ 0,80 para o conjunto de avaliação.

**Precision@k:** dos k chunks recuperados, quantos são realmente relevantes? Alta precision
reduz o ruído no contexto enviado ao modelo. Alvo: Precision@5 ≥ 0,65.

**MRR (Mean Reciprocal Rank):** mede se o chunk mais relevante está no topo dos resultados.
Importante para o efeito *lost in the middle* — um chunk relevante na posição 15 é menos útil
do que na posição 1.

### Métricas de Geração

**Faithfulness (fidelidade):** a resposta do modelo está suportada pelos chunks recuperados,
ou o modelo adicionou informações não presentes no contexto? Frameworks como RAGAS automatizam
essa avaliação.

**Answer Relevance:** a resposta é pertinente à query feita? Uma resposta fiel mas que responde
a uma pergunta diferente da feita não tem valor.

**Latência end-to-end:** tempo do submit da query até a primeira palavra da resposta. Alvo
para um assistente interno: P95 ≤ 5 segundos. Benchmarke separadamente retrieval, reranking
e geração para identificar gargalos.

### Conjunto de Avaliação

Construir um golden dataset de 150–250 pares (query, resposta esperada, chunk fonte) antes
do lançamento, cobrindo os três tipos de query (operacional, factual, analítico) e os cinco
tipos de fonte. Este dataset é o benchmark contra o qual cada mudança de pipeline é avaliada.
Sem ele, decisões de arquitetura são baseadas em intuição, não em evidência.

---

## 6. Riscos Operacionais e de Governança

Esta seção endereça riscos sistêmicos que não aparecem em provas de conceito mas dominam
projetos RAG corporativos em produção.

### 6.1 Atualização Incremental da Base (o Risco Mais Subestimado)

A ingestão inicial é um evento único. A partir do lançamento, documentos do SharePoint são
atualizados constantemente, páginas do Confluence são editadas semanalmente, e planilhas
ganham novas abas mensalmente. Um sistema RAG que não tem pipeline de atualização incremental
começa a degradar imediatamente após o lançamento.

Requisitos mínimos para a pipeline de atualização:

- **Detecção de mudanças:** usar webhooks do SharePoint e do Confluence para notificações em
  tempo real de criação, edição e exclusão de documentos. Para fontes sem webhook, polling
  com comparação de hash ou timestamp de modificação.
- **Re-ingestão seletiva:** apenas o documento modificado é re-processado e seus chunks
  antigos são removidos do índice. Re-ingestão total da base é computacionalmente
  inviável em escala.
- **Gerenciamento de versões de chunks:** cada chunk deve ter um ID estável vinculado ao
  documento fonte e à posição dentro dele. Quando um documento é atualizado, os chunks
  antigos são identificados pelo ID e removidos antes da inserção dos novos.
- **Propagação de dependências no Confluence:** quando uma página-pai é atualizada, avaliar
  se os chunks de páginas filhas que incorporaram conteúdo dela também precisam ser
  re-gerados.

### 6.2 Controle de Acesso e Permissões

Este é um requisito legal e de compliance, não uma feature opcional. O SharePoint e o
Confluence têm sistemas de permissões granulares: um funcionário do RH não deve ver
documentos financeiros confidenciais; um estagiário não deve ver contratos com cláusulas
de NDA.

O sistema RAG precisa preservar essas permissões. A abordagem recomendada é indexar as
ACLs (Access Control Lists) de cada documento como metadados no banco vetorial. No momento
do retrieval, adicionar um filtro obrigatório que restringe os candidatos apenas aos
documentos que o usuário autenticado tem permissão de ler. Isso requer:

- Integração com o sistema de identidade da empresa (Active Directory / Azure AD).
- Sincronização das ACLs como parte da pipeline de atualização incremental — quando
  uma permissão muda, os metadados dos chunks afetados devem ser atualizados.
- Verificação durante a geração da resposta: o modelo não deve citar um documento que o
  usuário não pode acessar, mesmo que o chunk tenha sido recuperado por erro.

Implementar filtros de permissão por usuário em um índice vetorial é tecnicamente complexo e
deve ser planejado desde a escolha do banco vetorial (nem todos suportam filtragem por
metadados de forma eficiente em escala).

### 6.3 Conflito entre Fontes e Documentos Contraditórios

Com 800 PDFs e 400 páginas de wiki, é quase certo que existirão documentos contraditórios
na base: uma política atualizada e sua versão anterior, um processo descrito diferentemente
em dois manuais de departamentos distintos. Em um sistema RAG sem tratamento de conflitos, o
modelo pode sintetizar as duas versões sem avisar, escolher arbitrariamente a mais antiga,
ou — pior — produzir uma resposta que mistura informações de versões diferentes como se
fossem coerentes.

Estratégias de mitigação:

- **Prioridade por data:** nos metadados de cada chunk, indexar a data de criação e de
  última modificação. Em caso de conflito entre fontes, o prompt do sistema deve instruir
  o modelo a priorizar a informação mais recente e sinalizar a existência de versões
  conflitantes.
- **Detecção de conflitos no reranking:** se dois chunks de documentos diferentes têm scores
  similares e conteúdo semanticamente contraditório (detectável por NLI — Natural Language
  Inference), sinalizar o conflito na resposta ao usuário em vez de silenciosamente
  escolher um.
- **Processo de depreciação de documentos:** definir com o time de conteúdo um processo para
  marcar documentos desatualizados com metadado `status: deprecated`, excluindo-os
  automaticamente do retrieval.

### 6.4 Qualidade dos Embeddings para Jargão Interno

Modelos de embedding como `text-embedding-3-large` foram treinados em texto geral. Siglas
internas, nomes de produtos proprietários e jargões departamentais específicos da NovaTech
podem ter representações vetoriais pobres ou colidir semanticamente com termos comuns.

Antes de escolher o modelo de embedding, executar uma avaliação com o golden dataset da
seção 5 usando pelo menos três modelos diferentes. Se o Recall@10 para queries com jargão
interno for significativamente menor do que para queries com linguagem comum, considerar:

- Fine-tuning do modelo de embedding com pares (query interna, trecho relevante) anotados
  pela equipe de domínio.
- Expansão de queries no momento do retrieval: antes de embedar a query do usuário, usar
  o LLM para gerar variantes com sinônimos e expansões de siglas.

### 6.5 Latência e Experiência do Usuário em Escala

A pipeline completa — retrieval semântico + retrieval léxico + fusão + reranking + chamada
ao GPT-4o — pode facilmente somar 8–15 segundos por query em um servidor sem otimização.
Para um assistente interno com dezenas de usuários simultâneos, isso é inaceitável.

Estratégias de mitigação por camada:

- **Cache de retrieval:** queries idênticas ou semanticamente próximas (similaridade de
  embedding > 0,95) retornam o resultado cacheado sem re-executar o retrieval. Eficaz
  para perguntas frequentes e repetitivas em contexto corporativo.
- **Streaming da resposta:** iniciar o stream de tokens do LLM assim que os chunks forem
  montados, sem esperar a resposta completa. Reduz a percepção de latência mesmo sem
  reduzir o tempo total.
- **Reranking assíncrono seletivo:** aplicar cross-encoder apenas para queries de alta
  ambiguidade (detectadas pelo baixo spread de scores do retrieval inicial). Queries com
  um chunk claramente dominante não precisam de reranking.
- **SLA de resposta:** definir P50 ≤ 3s e P95 ≤ 7s como metas. Monitorar por tipo de
  query e por fonte predominante nos chunks recuperados.

---

## Conclusão e Próximos Passos Recomendados

O sistema RAG proposto é tecnicamente viável, mas a complexidade real está em dois lugares
que as análises iniciais tendem a subestimar: a **diversidade e imperfeição das fontes de
dados** (especialmente fluxogramas embutidos e a natureza interligada do Confluence) e os
**requisitos operacionais pós-lançamento** (atualização incremental, controle de acesso e
monitoramento de qualidade contínuo).

**Recomendação de faseamento:**

**Fase 1 — Prova de Conceito (4–6 semanas):** Ingerir uma amostra representativa de 50 PDFs,
50 páginas do Confluence e 5 planilhas. Construir o golden dataset de avaliação. Medir Recall@10
e Faithfulness. Identificar as categorias de documentos com pior performance antes de escalar.

**Fase 2 — Pipeline de Produção (8–12 semanas):** Implementar o pipeline completo com suporte
a todos os tipos de fonte, incluindo Vision LLM para fluxogramas e indexação dupla para
planilhas. Implementar controle de acesso e pipeline de atualização incremental.

**Fase 3 — Otimização (contínua):** Fine-tuning de embeddings com feedback implícito de
uso (thumbs up/down nas respostas), redução de latência com caching e reranking seletivo,
e expansão do golden dataset com queries reais coletadas em produção.

O maior risco de projeto não é técnico: é lançar sem uma estratégia de atualização incremental
e sem métricas de qualidade, e só descobrir a degradação quando os usuários pararem de
confiar no sistema.
