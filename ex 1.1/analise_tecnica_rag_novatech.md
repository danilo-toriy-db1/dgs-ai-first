# Análise Técnica — Viabilidade do Assistente RAG NovaTech

---

## 1. Desafios por Tipo de Fonte

### PDFs com Tabelas Complexas (15+ colunas)

**Desafio principal**

A maioria dos parsers de PDF (PyMuPDF, pdfplumber, PDFMiner) serializa tabelas em texto linear — percorrendo célula por célula, linha por linha. Com 15 ou mais colunas, esse processo produz sequências de texto sem qualquer estrutura relacional legível. Cabeçalhos multi-nível (células mescladas que abrangem várias colunas) são frequentemente descartados ou duplicados de forma incorreta. O resultado é um chunk que parece ruído para o modelo, sem preservar o relacionamento entre coluna e valor.

**Impacto na qualidade das respostas**

Perguntas do tipo "Qual é o prazo de entrega para o fornecedor X na categoria Y?" dependem de coordenadas de linha e coluna para ser respondidas. Com a estrutura destruída, o modelo ou inventa uma resposta plausível (alucinação estrutural) ou responde que não encontrou a informação, mesmo que ela esteja presente no corpus.

**Estratégia de tratamento recomendada**

Usar uma pipeline de extração em dois estágios. Primeiro, detectar tabelas com uma biblioteca especializada como Camelot (modo lattice para tabelas com bordas explícitas) ou pdfplumber com detecção de bounding boxes. Segundo, converter cada tabela para Markdown de forma programática, preservando os cabeçalhos. Para tabelas grandes demais para caber em um chunk, particionar por grupo de linhas mantendo os cabeçalhos repetidos em cada partição. Complementar com um índice estruturado separado (por exemplo, indexar as tabelas como JSON no banco vetorial com metadados de coluna), permitindo retrieval híbrido: busca semântica para localizar a tabela certa + busca estruturada para extrair o valor exato.

---

### PDFs Escaneados (OCR Necessário)

**Desafio principal**

Documentos escaneados não contêm texto extraível — são imagens de páginas. O OCR introduz erros que variam conforme a qualidade da digitalização: caracteres confundidos (0/O, 1/l/I), palavras segmentadas incorretamente, perda de formatação (negrito, itálico, espaçamento) e degradação total em páginas rotacionadas ou com baixo contraste. Esses erros se propagam para o índice vetorial, corrompendo os embeddings dos chunks afetados.

**Impacto na qualidade das respostas**

Um chunk com texto corrompido gera embeddings que não correspondem às queries do usuário — o documento existe no corpus mas nunca é recuperado. Pior: quando recuperado por coincidência, o modelo recebe texto fragmentado e pode produzir respostas parcialmente erradas sem sinalizar incerteza.

**Estratégia de tratamento recomendada**

Aplicar OCR com Tesseract 5 (modo LSTM) ou, preferencialmente, Azure Document Intelligence / Google Document AI para documentos críticos, pois esses serviços têm precisão superior em layouts complexos. Antes do OCR, pré-processar as imagens: binarização adaptativa, correção de inclinação (deskewing) e aumento de resolução para no mínimo 300 DPI. Após o OCR, executar uma etapa de pós-correção com um modelo de linguagem leve (spell-checking contextual) para corrigir erros comuns. Armazenar o score de confiança do OCR como metadado do chunk; chunks abaixo de 85% de confiança devem ser sinalizados para revisão humana antes de entrar na base de produção.

---

### Wiki do Confluence (Links Internos e Macros)

**Desafio principal**

O Confluence exporta páginas em HTML ou via API REST. Nenhuma das duas abordagens é trivial: o HTML exportado contém macros renderizadas como elementos DOM opacos (painéis de aviso, status, roadmap, decisões de arquitetura) cujo conteúdo textual relevante é perdido ou transformado em texto sem contexto. Links internos entre páginas (`/wiki/spaces/ENG/pages/12345`) criam dependências de conteúdo que o chunking por página destrói — uma página que só faz sentido quando lida em conjunto com outra que ela referencia.

**Impacto na qualidade das respostas**

Perguntas que dependem de informações distribuídas entre múltiplas páginas interligadas — como "Qual é o processo de onboarding de um novo fornecedor?" — podem retornar respostas incompletas se a página principal for recuperada mas as subpáginas referenciadas não. Macros como Jira Issues ou Table of Contents que listam itens dinamicamente ficam completamente vazias no texto extraído.

**Estratégia de tratamento recomendada**

Usar a API REST do Confluence para extração em vez de exportação em lote. A API retorna o corpo da página em storage format (XML/XHTML), permitindo parsear macros conhecidas por nome e extrair seu conteúdo de forma semântica. Para links internos, construir um grafo de dependências de páginas durante a ingestão e implementar chunking hierárquico: a página-pai e suas páginas filhas referenciadas são agrupadas no mesmo "documento lógico" antes do chunking. Isso preserva o contexto interligado. Labels e metadados do Confluence (espaço, criador, data de modificação, etiquetas) devem ser indexados como metadados filtráveis, permitindo retrieval por espaço ou por tipo de documento.

---

### Planilhas com Fórmulas Interdependentes

**Desafio principal**

Fórmulas como `=VLOOKUP(A2,Budget!$A:$D,3,0)` ou `=IF(C5>Metas!B2,"OK","Rever")` não têm valor informativo isoladas — elas são referências a outras células e abas. Um sistema RAG que indexa o texto bruto de uma planilha captura literalmente a string da fórmula, não o valor calculado. Mesmo que o parser execute as fórmulas e extraia os valores, o contexto semântico é perdido: o número "142.500" sem saber que é a "meta de vendas do Q3 para a região Sul" é inútil para o modelo.

**Impacto na qualidade das respostas**

Perguntas analíticas como "Qual região está abaixo da meta neste trimestre?" requerem que o modelo entenda a relação entre células, abas e valores calculados. Sem esse contexto, o modelo ou não responde ou responde com base apenas nos valores recuperados, sem compreender o que eles representam.

**Estratégia de tratamento recomendada**

Usar openpyxl ou xlwings para ler planilhas com valores já calculados (não as fórmulas em si). Para cada aba, serializar os dados como uma tabela Markdown com cabeçalhos explícitos. Incluir no início de cada chunk uma descrição gerada automaticamente da aba: nome, propósito inferido dos cabeçalhos, intervalo de datas se detectável, e a lista de outras abas que a alimentam (dependências de fórmulas). Para planilhas de orçamento ou metas com estrutura previsível, considerar uma indexação estruturada adicional como documentos JSON com campos nomeados, permitindo queries paramétricas diretas além da busca semântica.

---

## 2. Estimativa da Base em Tokens

### PDFs

```
800 documentos × 10 páginas/doc = 8.000 páginas
8.000 páginas × 250 palavras/página = 2.000.000 palavras
2.000.000 palavras × 1,33 tokens/palavra = 2.660.000 tokens
```

### Wiki do Confluence

```
400 páginas × 1.500 palavras/página = 600.000 palavras
600.000 palavras × 1,33 tokens/palavra = 798.000 tokens
```

### Planilhas Excel

Estimativa: cada planilha, após serialização para texto (cabeçalhos + valores das células + descrições de abas), produz em média 800 palavras (equivalente a ~3 abas com 50 linhas cada).

```
50 arquivos × 800 palavras/arquivo = 40.000 palavras
40.000 palavras × 1,33 tokens/palavra = 53.200 tokens
```

### Total Consolidado

| Fonte             | Palavras      | Tokens         |
|-------------------|---------------|----------------|
| PDFs              | 2.000.000     | 2.660.000      |
| Confluence        | 600.000       | 798.000        |
| Planilhas Excel   | 40.000        | 53.200         |
| **Total**         | **2.640.000** | **3.511.200**  |

**A base tem aproximadamente 3,5 milhões de tokens**, o que é viável para um sistema RAG. Para referência: indexar tudo em um único contexto de LLM seria impossível — esse volume equivale a ~27 janelas completas do GPT-4o. O RAG é, portanto, a arquitetura obrigatória, não opcional.

---

## 3. Análise de Orçamento de Contexto

### Distribuição da Janela de Contexto (128.000 tokens)

| Componente                        | Tokens reservados | Tokens disponíveis após dedução |
|-----------------------------------|-------------------|---------------------------------|
| Janela total do GPT-4o            | —                 | 128.000                         |
| System prompt + instruções fixas  | 2.000             | 126.000                         |
| Histórico de conversa (média)     | 1.000             | 125.000                         |
| **Espaço disponível para chunks** | **—**             | **125.000**                     |

### Quantos Chunks Cabem por Query?

```
125.000 tokens disponíveis ÷ 500 tokens/chunk = 250 chunks por query
```

Na prática, enviar 250 chunks por query é tecnicamente possível mas operacionalmente contraproducente por três razões:

**Custo:** cada query consumiria 128k tokens de input, multiplicando o custo por chamada.

**Latência:** prompts muito longos aumentam o tempo de inferência do modelo.

**Qualidade:** o efeito *lost in the middle* degrada a qualidade das respostas com contextos muito extensos.

### Implicações para a Estratégia de Retrieval

O limite prático recomendado é de **8 a 15 chunks por query** (4.000–7.500 tokens de contexto recuperado), reservando espaço para o prompt de sistema e a resposta do modelo. Isso implica que o sistema de retrieval precisa ser altamente preciso — o burden de qualidade se desloca do modelo (que não vê tudo) para o retriever (que precisa selecionar os chunks certos em um corpus de 3,5M tokens).

Para atingir essa precisão, a estratégia deve combinar:

**Retrieval semântico:** busca por embeddings (cosine similarity) para correspondência de intenção.

**Retrieval léxico (BM25):** para termos técnicos, siglas e nomes próprios que embeddings tendem a normalizar incorretamente.

**Reranking:** um modelo de cross-encoder (como Cohere Rerank ou BGE-Reranker) aplicado sobre os top-50 candidatos do retrieval para selecionar os 10 mais relevantes antes de montar o prompt final.

### Efeito *Lost in the Middle* no Posicionamento dos Chunks

Pesquisas empíricas (Liu et al., 2023) demonstram que modelos de linguagem tendem a utilizar mais efetivamente informações posicionadas no início e no final do contexto, com degradação sistemática para informações no meio.

**Recomendação de posicionamento:**

Posicionar o chunk mais relevante (maior score de relevância) no início do bloco de contexto recuperado, seguido pelos chunks de menor relevância no meio, e o segundo chunk mais relevante ao final. Essa estratégia de "sanduíche" maximiza a utilização das informações mais importantes pelo modelo.

Além disso, limitar o número de chunks recuperados — preferindo 8 chunks altamente relevantes a 20 mediocres — reduz a probabilidade de informações críticas caírem na zona de atenção degradada do meio do contexto.

---

## 4. Estratégia de Chunking Recomendada

### Perfil de Queries Esperadas

O usuário típico da NovaTech fará perguntas em três categorias com características distintas de retrieval:

**Perguntas operacionais** ("Como faço para solicitar um equipamento?", "Qual é o prazo para renovação de contratos?"): requerem chunks pequenos e precisos — a resposta está em uma seção específica de um documento, não espalhada. Chunks de 300–400 tokens com overlap mínimo funcionam bem aqui.

**Perguntas factuais** ("Qual é o CNPJ do fornecedor X?", "Quem é o responsável pelo projeto Y?"): dependem de recuperação de entidades específicas. Chunks muito grandes diluem a entidade no ruído; chunks pequenos com contexto suficiente para identificar a entidade são ideais.

**Perguntas analíticas** ("Compare o orçamento previsto vs. realizado do Q2", "Quais projetos estão em risco de atraso?"): requerem múltiplos chunks de fontes diferentes, com contexto suficiente para o modelo sintetizar. Chunks de 600–800 tokens são mais adequados, pois preservam mais contexto por unidade recuperada.

### Estratégia por Fonte

**PDFs com conteúdo narrativo (políticas, procedimentos):** chunking por seção semântica — identificar quebras de seção pelo header hierárquico (H1, H2, H3) e criar um chunk por seção, com tamanho alvo de 400–600 tokens. Adicionar um overlap de 50–80 tokens entre chunks consecutivos para não quebrar frases que cruzem a fronteira. Incluir o título da seção no início de cada chunk como contexto implícito.

**PDFs com tabelas:** chunks de tabela são tratados separadamente do texto narrativo. Cada tabela vira um chunk próprio (independente do tamanho, até o limite de 1.000 tokens; tabelas maiores são particionadas por grupo de linhas). O chunk de tabela inclui obrigatoriamente o título do documento, o título da seção onde aparece e os cabeçalhos das colunas repetidos.

**Confluence:** chunking hierárquico. A unidade mínima é a seção de uma página (delimitada por cabeçalhos). Páginas curtas (abaixo de 300 tokens) são agregadas com suas páginas irmãs na mesma hierarquia. Metadados do Confluence (espaço, ancestrais, labels) são indexados como campos filtráveis para permitir retrieval contextual por domínio.

**Planilhas:** cada aba é um chunk único, precedido por um cabeçalho descritivo gerado automaticamente. Abas com mais de 1.000 tokens são particionadas por blocos de linhas, sempre repetindo os cabeçalhos das colunas. Criar também chunks de sumário executivo para planilhas de orçamento — uma representação em linguagem natural dos valores-chave da aba, facilitando o retrieval semântico.

### Mitigação do Efeito *Lost in the Middle* na Fase de Chunking

Além do posicionamento no prompt (abordado na seção 3), o chunking pode mitigar o efeito *lost in the middle* estruturalmente: chunks menores e mais precisos reduzem a quantidade de informação que precisa ser mantida no contexto, diminuindo a probabilidade de informação relevante cair na zona de atenção degradada. Preferir chunks de 400–600 tokens com alta precisão a chunks de 1.000+ tokens com conteúdo misto é a heurística principal.

### Resumo das Decisões de Chunking

| Fonte                     | Tamanho alvo  | Overlap   | Unidade de chunking       | Metadados obrigatórios                          |
|---------------------------|---------------|-----------|---------------------------|-------------------------------------------------|
| PDFs narrativos           | 400–600 tok   | 60–80 tok | Seção semântica (header)  | Título do doc, seção, número da página          |
| PDFs com tabelas          | até 1.000 tok | 0         | Tabela completa           | Título do doc, seção, cabeçalhos das colunas    |
| PDFs escaneados (pós-OCR) | 300–500 tok   | 80 tok    | Bloco de parágrafos       | Score de confiança OCR, título do doc           |
| Confluence                | 300–600 tok   | 50 tok    | Seção da página           | Espaço, página-pai, labels, data de atualização |
| Planilhas                 | até 1.000 tok | 0         | Aba (com cabeçalhos)      | Nome do arquivo, nome da aba, dependências      |
