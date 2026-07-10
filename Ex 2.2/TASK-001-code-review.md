# Code Review — TASK-001 Query Endpoint (NovaTech Assistant)

> **Nota:** Este código corresponde à implementação antecipada de TASK-006
> (validator.ts) e do esqueleto de TASK-011 (handler.ts), executada como
> demonstração conforme orientação do exercício. A TASK-001 real (types.ts)
> é pré-requisito e seria implementada antes em produção.

**Revisor:** Dev Sênior (pré-review)
**Stack:** TypeScript + Azure Functions v4 + Zod
**Arquivos analisados:** `src/functions/query/validator.ts`, `src/functions/query/handler.ts`

---

## Resumo

Revisei os dois arquivos gerados pelo GitHub Copilot com foco nos requisitos da task (API v4, validação Zod → 400, erros inesperados → 500 sem stack trace, logging sem PII, TypeScript strict sem `any` não justificado). Foram identificados **2 problemas reais**, ambos com impacto concreto em produção. Os demais pontos dos requisitos estão corretamente atendidos — detalhado na seção final.

---

### P1 — Rota duplicada (`api/api/query`)

**Arquivo e localização:** `handler.ts`, dentro de `app.http('query', { ... route: 'api/query' ... })`, linha ~55

**O que está errado:** No Azure Functions v4, o `host.json` define por padrão `routePrefix: "api"` (a menos que tenha sido explicitamente sobrescrito para `""`). O valor passado em `route` é concatenado *depois* desse prefixo. Ao definir `route: 'api/query'`, a URL real do endpoint se torna `/api/api/query`, e não `/api/query` como provavelmente pretendido.

**Por que é um problema real:** Não é estilístico — é um bug funcional. Qualquer client, teste de integração ou documentação que chame `/api/query` (o caminho "óbvio") vai receber 404. É um erro comum quando código v4 é gerado copiando hábitos de configuração de rota do v3/Express. Só é pego em code review se o revisor testar o endpoint de ponta a ponta ou checar o `host.json`.

**Correção proposta:**
```typescript
app.http('query', {
  methods: ['POST'],
  authLevel: 'function',
  // routePrefix "api" já vem do host.json (padrão) — não duplicar aqui
  route: 'query',
  handler: queryHandler,
});
```
> Se a intenção for realmente ter `/api/query` sem prefixo global, a alternativa é setar `"routePrefix": ""` no `host.json` e manter `route: 'api/query'`. De qualquer forma, isso precisa ser uma decisão explícita e documentada, não uma duplicação acidental.

---

### P2 — JSON malformado retorna 500 em vez de 400

**Arquivo e localização:** `handler.ts`, função `queryHandler`, linha ~9 (`const body: unknown = await request.json();`)

**O que está errado:** `request.json()` lança exceção se o corpo da requisição não for um JSON válido (body vazio, JSON truncado, `Content-Type` incorreto, etc.). Essa exceção é capturada pelo `catch` genérico do handler, que trata **qualquer** erro como "erro inesperado" e retorna 500. Um input malformado do cliente — que é claramente um erro de validação — acaba classificado como falha interna do servidor.

**Por que é um problema real:** Viola diretamente o contrato definido nos requisitos ("400 quando input inválido" vs "500 para erros inesperados"). Na prática: clients que enviam JSON quebrado (bug de integração, proxy corrompendo payload, etc.) geram alertas de erro 500 em produção/observabilidade como se fosse falha do sistema, poluindo métricas de erro real e dificultando triagem de incidentes. Também é semanticamente incorreto do ponto de vista de API design — 500 deveria significar "o servidor falhou", não "o cliente mandou algo errado".

**Correção proposta:**
```typescript
async function queryHandler(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    logger.warn({ event: 'query_invalid_json' });
    return {
      status: 400,
      jsonBody: {
        error: 'Invalid request',
        details: { formErrors: ['Malformed JSON body'], fieldErrors: {} },
      },
    };
  }

  try {
    const validation = QueryRequestSchema.safeParse(body);
    // ... resto do fluxo de validação/processamento permanece igual
  } catch (error: unknown) {
    logger.error({
      event: 'query_handler_error',
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    return { status: 500, jsonBody: { error: 'Internal server error' } };
  }
}
```
Separar o parsing do JSON do restante do try/catch garante que apenas erros verdadeiramente inesperados (bug de código, falha de dependência) cheguem ao 500.

---

## O que está correto (sem inventar problema)

- **Sintaxe v4 (`app.http()`)** — correta, nenhuma referência a `module.exports`/v3.
- **TypeScript strict / `any`** — não há uso de `any` em nenhum arquivo; `catch (error: unknown)` está corretamente tipado e tratado com type narrowing (`error instanceof Error`).
- **500 sem stack trace no corpo da resposta** — confirmado: o `catch` externo só expõe `{ error: 'Internal server error' }` ao cliente; o `error.message` vai só para o log, nunca para o response.
- **PII no logging** — o conteúdo da pergunta (`question`) nunca é logado; apenas `questionLength` é registrado no evento `query_received`, o que é boa prática de log seguro.
- **Zod → 400 com detalhes** — no caminho feliz de validação (payload JSON válido, mas com campos incorretos), o fluxo está correto: `safeParse` + `flatten()` no body da resposta.

---

## Veredicto

### ⚠️ Requer ajustes antes do code review

Faltam corrigir os dois pontos acima antes de abrir o PR formal:

1. Confirmar o `routePrefix` no `host.json` e ajustar `route` para não duplicar `api/`.
2. Isolar o parsing de JSON do tratamento de erro genérico, garantindo que payload malformado retorne 400, não 500.

Nenhum dos dois é bloqueador de segurança ou de arquitetura — são bugs de comportamento que um code review "de verdade" (não só "funciona localmente") certamente pegaria ao testar a rota real ou enviar um body inválido. Com essas duas correções aplicadas, o código atende aos requisitos listados.
