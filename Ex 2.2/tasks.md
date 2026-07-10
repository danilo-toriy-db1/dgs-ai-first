# Tasks — Query Endpoint

## ⚠️ Suposições assumidas (pendente validação do Tech Lead)

ADR-0002 e ADR-0003, citadas no `plan.md`, não foram encontradas no repositório.
Os arquivos `types.ts`, `config.ts`, `errors.ts`, `logger.ts` e
`/prompts/system-prompt.md` existem mas estão vazios. Para manter as tasks
abaixo atômicas e com critérios verificáveis, assumi os seguintes valores.
**Eles não substituem as ADRs — a TASK-014 formaliza essa pendência.**

| Item | Suposição adotada | Motivo |
|---|---|---|
| Context budget | ~2K tokens system + ~8K tokens chunks (valor da seção *Approach* do plan.md) | *Prior Decisions* cita ADR-0002 com ~4K system, mas a ADR não existe para confirmar. Optei pelo valor mais explícito e recente do próprio plan. |
| Vigência de documentos (ADR-0003) | Campo `vigenciaDate` (ISO 8601) no metadado do chunk; regra "mais recente vence" ao ordenar resultados | Nenhuma regra estava descrita; esta é a interpretação mínima e mais comum para esse tipo de conflito. |
| Tamanho máximo de `question` | 1–2000 caracteres | Não especificado no plan; valor de segurança razoável para um chat de atendimento. |
| Retry / backoff | 3 tentativas, delay base 200ms, fator 2 (200ms → 400ms → 800ms), sem jitter | Plan exige "retry com exponential backoff" mas não define parâmetros. |
| `/prompts/system-prompt.md` vazio | `prompt-builder.ts` lê o arquivo em runtime (não hardcoda conteúdo) | Assim as tasks não dependem do conteúdo final do prompt. |
| Índice do Azure AI Search / Azure OpenAI reais | Testes de integração usam `nock` para simular respostas fixas | Dependencies do plan.md indicam que o índice real ainda não está populado. |
| Convenção de path para ADRs | `docs/adr/ADR-NNNN-titulo.md` | Não há convenção declarada no repositório; ajustar se houver outra. |

Se qualquer suposição acima estiver errada, as tasks TASK-006, TASK-007,
TASK-008 e TASK-009 (as que dependem de números/regras concretas) precisarão
ser revisadas.

---
### TASK-001 — Definir tipos de domínio do query endpoint

**Arquivo(s) afetado(s):** `src/shared/types.ts` (atualmente vazio)

**Descrição:** Definir as interfaces/types TypeScript usados por todo o fluxo do query endpoint: request de entrada, chunk de busca, resposta final e opções de retry. Esses tipos serão importados por `validator.ts`, `search.ts`, `prompt-builder.ts`, `completion.ts` e `response-builder.ts`.

**Critérios de aceite:**
- [ ] O arquivo exporta `QueryRequest { question: string }`
- [ ] O arquivo exporta `Chunk { id: string; content: string; sourceDocument: string; vigenciaDate?: string; score: number }`
- [ ] O arquivo exporta `QueryResponse { answer: string; sourceDocument: string }`
- [ ] O arquivo exporta `RetryOptions { maxAttempts: number; baseDelayMs: number; factor: number }`
- [ ] `npx tsc --noEmit` executa sem erros
- [ ] Um arquivo de teste de tipos (`src/shared/types.test-d.ts`) importa cada type e falha a compilação (`tsc --noEmit` retorna erro) se um campo obrigatório for omitido em um objeto literal de teste

**Dependências:** Nenhuma

**Estimativa:** P

---
### TASK-002 — Implementar configuração de ambiente

**Arquivo(s) afetado(s):** `src/shared/config.ts` (atualmente vazio)

**Descrição:** Implementar `loadConfig()` que lê e valida as variáveis de ambiente necessárias (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`, `AZURE_SEARCH_INDEX_NAME`, `SYSTEM_PROMPT_PATH`), retornando um objeto tipado. Deve lançar um erro descritivo quando uma variável obrigatória estiver ausente.

**Critérios de aceite:**
- [ ] Teste unitário (Vitest): com todas as env vars setadas em `process.env`, `loadConfig()` retorna um objeto contendo as 7 chaves esperadas com os valores exatos setados
- [ ] Teste unitário: removendo `AZURE_OPENAI_API_KEY` do `process.env` antes de chamar `loadConfig()`, a chamada lança erro cuja mensagem contém a string `"AZURE_OPENAI_API_KEY"`
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001

**Estimativa:** P

---
### TASK-003 — Implementar erros customizados

**Arquivo(s) afetado(s):** `src/shared/errors.ts` (atualmente vazio)

**Descrição:** Implementar classes de erro `ValidationError` (statusCode 400), `ExternalServiceError` (statusCode 502) e `NotFoundError` (statusCode 404), todas estendendo uma `AppError` base com método `toJSON()` retornando `{ error: string, details?: unknown }`.

**Critérios de aceite:**
- [ ] Teste unitário: `new ValidationError("question inválido", { field: "question" }).toJSON()` retorna `{ error: "ValidationError", details: { field: "question" } }`
- [ ] Teste unitário: `new ExternalServiceError("timeout").statusCode === 502`
- [ ] Teste unitário: `new NotFoundError("doc não encontrado").statusCode === 404`
- [ ] Teste unitário: todas as classes de erro são instâncias de `Error` (`instanceof Error === true`)
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001

**Estimativa:** P

---
### TASK-004 — Implementar logger estruturado com pino

**Arquivo(s) afetado(s):** `src/shared/logger.ts` (atualmente vazio)

**Descrição:** Exportar um logger pino singleton com campos base `{ service: "query-endpoint" }` e uma função `createRequestLogger(requestId: string)` que retorna um child logger incluindo `requestId` em todo log emitido.

**Critérios de aceite:**
- [ ] Teste unitário: capturando a saída do logger via stream em memória (`pino.destination` de teste), `logger.info("teste")` produz uma linha JSON parseável contendo `"service":"query-endpoint"`
- [ ] Teste unitário: `createRequestLogger("abc-123").info("teste")` produz JSON contendo `"requestId":"abc-123"`
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001

**Estimativa:** P

---
### TASK-005 — Implementar helper de retry com backoff exponencial

**Arquivo(s) afetado(s):** `src/shared/retry.ts` (novo arquivo)

**Descrição:** Implementar `withRetry<T>(fn: () => Promise<T>, options: RetryOptions): Promise<T>` que executa `fn`, e em caso de rejeição, aguarda `baseDelayMs * factor^(tentativa-1)` antes de tentar novamente, até `maxAttempts`. Ao esgotar as tentativas, propaga o último erro capturado.

**Critérios de aceite:**
- [ ] Teste unitário (com `jest.useFakeTimers`/`vi.useFakeTimers`): `fn` mockada rejeita nas 2 primeiras chamadas e resolve na 3ª; usando `{ maxAttempts: 3, baseDelayMs: 200, factor: 2 }`, `withRetry` resolve com o valor esperado e `fn` foi chamada exatamente 3 vezes
- [ ] Teste unitário: os delays entre chamadas avançados via `vi.advanceTimersByTime` são exatamente 200ms e depois 400ms
- [ ] Teste unitário: `fn` mockada rejeita em todas as `maxAttempts` chamadas; `withRetry` rejeita com o mesmo erro lançado por `fn` na última tentativa
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001

**Estimativa:** M

---
### TASK-006 — Implementar validação de input e output (Zod)

**Arquivo(s) afetado(s):** `src/functions/query/validator.ts` (novo)

**Descrição:** Implementar `QuerySchema` (Zod) para o input `{ question: string, min 1, max 2000 caracteres }` e função `validateQuery(body: unknown): QueryRequest` que lança `ValidationError` em caso de falha. Implementar também `ResponseSchema` para `{ answer: string, sourceDocument: string }` e `validateResponse(data: unknown): QueryResponse`.

**Critérios de aceite:**
- [ ] Teste unitário: `validateQuery({ question: "Qual o prazo de entrega?" })` retorna `{ question: "Qual o prazo de entrega?" }`
- [ ] Teste unitário: `validateQuery({ question: "" })` lança `ValidationError`
- [ ] Teste unitário: `validateQuery({})` lança `ValidationError` cujo `.toJSON().details` referencia o campo `"question"`
- [ ] Teste unitário: `validateQuery({ question: "a".repeat(2001) })` lança `ValidationError`
- [ ] Teste unitário: `validateResponse({ answer: "x", sourceDocument: "doc.pdf" })` retorna o objeto validado sem alterações
- [ ] Teste unitário: `validateResponse({ answer: "x" })` (sem `sourceDocument`) lança erro
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001, TASK-003

**Estimativa:** M

---
### TASK-007 — Implementar serviço de busca (search.ts)

**Arquivo(s) afetado(s):** `src/services/search.ts` (novo)

**Descrição:** Implementar `searchChunks(question: string, deps: { embeddingClient, searchClient }): Promise<Chunk[]>` que gera o embedding da pergunta, busca os top-5 chunks no Azure AI Search, e ordena o resultado por `vigenciaDate` decrescente quando o campo estiver presente (regra assumida para documentos contraditórios — ver seção de suposições). Chamadas aos clients Azure devem usar `withRetry` (TASK-005).

**Critérios de aceite:**
- [ ] Teste unitário: com `searchClient` mockado retornando 5 resultados, `searchChunks` retorna um array de 5 `Chunk`
- [ ] Teste unitário: dados dois chunks com o mesmo `content` mas `vigenciaDate` diferentes, o resultado retorna o chunk com data mais recente na posição anterior ao mais antigo
- [ ] Teste unitário: `searchClient` mockado rejeita nas 2 primeiras chamadas e resolve na 3ª; `searchChunks` resolve com sucesso e o mock foi chamado exatamente 3 vezes
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001, TASK-003, TASK-005

**Estimativa:** G

---
### TASK-008 — Implementar montagem de prompt (prompt-builder.ts)

**Arquivo(s) afetado(s):** `src/services/prompt-builder.ts` (novo)

**Descrição:** Implementar `buildPrompt(chunks: Chunk[], question: string, systemPromptPath: string): { systemPrompt: string; userPrompt: string }`. O system prompt é lido do arquivo em runtime (`fs.readFileSync`), sem conteúdo hardcoded. Os chunks são concatenados no `userPrompt` respeitando o orçamento assumido de ~8K tokens (aproximação de 4 caracteres por token); se o total exceder o limite, remove-se primeiro os chunks de menor `score` até caber no orçamento.

**Critérios de aceite:**
- [ ] Teste unitário: com `fs.readFileSync` mockado retornando string vazia (simulando o `system-prompt.md` vazio atual), `buildPrompt` retorna `systemPrompt === ""` sem lançar erro
- [ ] Teste unitário: com 5 chunks pequenos (total < 8000 tokens), `userPrompt` contém o `content` de todos os 5
- [ ] Teste unitário: com chunks cujo total de caracteres excede `8000 * 4`, `buildPrompt` remove chunks começando pelo menor `score` até o total ficar dentro do limite, mantendo os restantes ordenados por `score` decrescente
- [ ] Teste unitário: `userPrompt` contém a string exata da `question` passada
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001, TASK-002

**Estimativa:** M

---
### TASK-009 — Implementar integração com Azure OpenAI (completion.ts)

**Arquivo(s) afetado(s):** `src/services/completion.ts` (novo)

**Descrição:** Implementar `getCompletion(systemPrompt: string, userPrompt: string, openAIClient): Promise<{ answer: string }>` que chama o Azure OpenAI chat completion. Erros com status 429 ou 5xx são tratados como retryable via `withRetry`; erros com status 400 são relançados imediatamente como `ExternalServiceError`, sem retry.

**Critérios de aceite:**
- [ ] Teste unitário: `openAIClient` mockado retornando sucesso na 1ª chamada; `getCompletion` resolve com `{ answer: <texto mockado> }`
- [ ] Teste unitário: `openAIClient` mockado rejeitando com `{ status: 429 }` nas 2 primeiras chamadas e resolvendo na 3ª; `getCompletion` resolve com sucesso e o mock foi chamado exatamente 3 vezes
- [ ] Teste unitário: `openAIClient` mockado rejeitando com `{ status: 400 }`; `getCompletion` rejeita com `ExternalServiceError` e o mock foi chamado exatamente 1 vez (sem retry)
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001, TASK-003, TASK-005

**Estimativa:** M

---
### TASK-010 — Implementar montagem da resposta final (response-builder.ts)

**Arquivo(s) afetado(s):** `src/functions/query/response-builder.ts` (novo)

**Descrição:** Implementar `buildResponse(completion: { answer: string }, chunks: Chunk[]): QueryResponse` que seleciona o `sourceDocument` do chunk com maior `score`, monta o objeto final e o valida com `validateResponse` (TASK-006) antes de retorná-lo.

**Critérios de aceite:**
- [ ] Teste unitário: dado `completion = { answer: "resposta" }` e 3 chunks com scores `[0.4, 0.9, 0.7]`, `sourceDocument` no resultado é o `sourceDocument` do chunk com score `0.9`
- [ ] Teste unitário: se `validateResponse` lançar erro (simulando shape inválido via mock), `buildResponse` propaga o mesmo erro sem capturá-lo
- [ ] `npx tsc --noEmit` passa

**Dependências:** TASK-001, TASK-006

**Estimativa:** P

---
### TASK-011 — Implementar HTTP trigger do query endpoint (handler.ts)

**Arquivo(s) afetado(s):** `src/functions/query/handler.ts` (novo)

**Descrição:** Implementar a Azure Function HTTP trigger `POST /api/query`, orquestrando `validateQuery` → `searchChunks` → `buildPrompt` → `getCompletion` → `buildResponse`. Deve gerar um `requestId` (uuid) por requisição, usar `createRequestLogger(requestId)` para logar início, fim e erros, e mapear erros customizados para status HTTP (`ValidationError` → 400, `ExternalServiceError` → 502, qualquer outro erro não tratado → 500 com body `{ "error": "InternalServerError" }`).

**Critérios de aceite:**
- [ ] `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:7071/api/query -H "Content-Type: application/json" -d '{"question": ""}'` retorna `400`
- [ ] `curl -s -X POST http://localhost:7071/api/query -H "Content-Type: application/json" -d '{"question": ""}'` retorna body JSON contendo `"error":"ValidationError"` e `details` referenciando `"question"`
- [ ] Com dependências injetadas mockadas (search e completion retornando sucesso), `curl -s -X POST http://localhost:7071/api/query -H "Content-Type: application/json" -d '{"question":"Qual o prazo de entrega?"}'` retorna HTTP 200 com body contendo as chaves `"answer"` e `"sourceDocument"`
- [ ] Teste unitário: quando uma dependência interna lança um erro genérico (não `AppError`), a resposta HTTP tem status 500 e body `{"error":"InternalServerError"}`
- [ ] Teste unitário: cada requisição gera pelo menos uma linha de log estruturado contendo o `requestId` usado na resposta

**Dependências:** TASK-002, TASK-003, TASK-004, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010

**Estimativa:** G

---
### TASK-012 — Teste unitário completo do handler (mockado, sem chamadas externas)

**Arquivo(s) afetado(s):** `src/functions/query/handler.test.ts` (novo)

**Descrição:** Suite de testes que mocka integralmente `search.ts` e `completion.ts` (via `vi.mock`/`jest.mock`), cobrindo os cenários: sucesso completo, input inválido, falha de busca após esgotar retries, e falha de completion após esgotar retries. Nenhuma chamada de rede real deve ocorrer.

**Critérios de aceite:**
- [ ] `npx vitest run src/functions/query/handler.test.ts` executa e passa com 0 falhas
- [ ] A suíte cobre explicitamente os 4 cenários citados (sucesso, input inválido, falha de search, falha de completion), um `it()`/`test()` por cenário
- [ ] Nenhum teste do arquivo realiza chamada HTTP real — verificável pela ausência de qualquer client HTTP não mockado no arquivo de teste (`search.ts` e `completion.ts` substituídos por `vi.mock`)

**Dependências:** TASK-011

**Estimativa:** M

---
### TASK-013 — Teste de integração do query endpoint

**Arquivo(s) afetado(s):** `src/functions/query/handler.integration.test.ts` (novo), `package.json` (novo script `test:integration`)

**Descrição:** Subir a Azure Function localmente (`func start`) e executar uma requisição HTTP real contra o handler, interceptando as chamadas para Azure AI Search e Azure OpenAI via `nock` com respostas fixas (o índice real e o `system-prompt.md` final ainda não existem — ver suposições no topo do documento). Valida o contrato HTTP ponta a ponta sem depender de infraestrutura Azure real.

**Critérios de aceite:**
- [ ] Com `func start` em execução e `nock` interceptando os 2 endpoints externos com respostas fixas, `curl -s -X POST http://localhost:7071/api/query -H "Content-Type: application/json" -d '{"question":"Qual o prazo de entrega?"}'` retorna HTTP 200 e um JSON cujo `answer` e `sourceDocument` correspondem exatamente aos valores fixados no mock do `nock`
- [ ] `npm run test:integration` executa esse mesmo fluxo de forma automatizada e retorna código de saída `0` em caso de sucesso, ou não-zero se o status HTTP não for 200
- [ ] O script de teste falha explicitamente (assert) se qualquer chamada HTTP não interceptada pelo `nock` for detectada (`nock.disableNetConnect()`)

**Dependências:** TASK-011, TASK-012

**Estimativa:** G

---
### TASK-014 — Formalizar ADR-0002 e ADR-0003 com as decisões assumidas na implementação

**Arquivo(s) afetado(s):** `docs/adr/ADR-0002-context-budget.md` (novo), `docs/adr/ADR-0003-documentos-contraditorios.md` (novo)

**Descrição:** ADR-0002 (orçamento de contexto) e ADR-0003 (tratamento de documentos contraditórios) são citadas no `plan.md` mas não existem no repositório. Esta task documenta formalmente, para revisão do Tech Lead, as decisões que foram assumidas durante a implementação (orçamento ~2K system / ~8K chunks; regra "mais recente vence" via campo `vigenciaDate`), permitindo aprovação ou correção retroativa.

**Critérios de aceite:**
- [ ] `docs/adr/ADR-0002-context-budget.md` existe e contém as seções `## Status`, `## Contexto`, `## Decisão`, `## Consequências`
- [ ] `docs/adr/ADR-0003-documentos-contraditorios.md` existe com as mesmas seções e descreve explicitamente o campo `vigenciaDate` e a regra "mais recente vence"
- [ ] Ambos os arquivos têm `## Status` igual a `Proposta` (não `Aceita`), indicando que pendem revisão do Tech Lead
- [ ] Ambos os arquivos citam explicitamente as tasks (TASK-007, TASK-008) cuja implementação depende dessa decisão

**Dependências:** TASK-007, TASK-008

**Estimativa:** P