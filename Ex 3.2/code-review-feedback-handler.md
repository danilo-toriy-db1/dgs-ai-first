# Code Review — `feedback-handler.ts`

**Projeto:** NovaTech Assistant
**Módulo revisado:** `/src/functions/feedback/handler.ts` (gerado pelo GitHub Copilot)
**Revisor:** Dev Sênior — code review pré-merge

---

## P1 — Nenhuma validação de input (ausência de Zod)

**Classificação:** Violação do AGENTS.md | Problema de segurança
**Localização:** `const body = await request.json() as any;` e a construção do objeto `feedback`
**O que está errado:** O corpo da requisição é lido e usado diretamente, sem nenhum schema de validação. O projeto exige Zod para todo input externo, e aqui não há nenhum.
**Por que é um problema real:** Qualquer cliente pode enviar `rating` fora de escala, `comment` gigante (custo de armazenamento no Cosmos, possível estouro do limite de 2MB por item), `queryId` inválido ou ausente, ou campos completamente diferentes do esperado. Isso corrompe a integridade dos dados de feedback e pode quebrar consumidores downstream (dashboards, relatórios) que assumem um shape confiável.

**Correção proposta:**
```typescript
import { z } from 'zod';

const feedbackSchema = z.object({
  queryId: z.string().uuid(),
  rating: z.number().int().min(1).max(5),
  comment: z.string().max(2000).optional(),
  attendantEmail: z.string().email()
});

const parseResult = feedbackSchema.safeParse(await request.json());
if (!parseResult.success) {
  return {
    status: 400,
    jsonBody: { error: 'Payload inválido', details: parseResult.error.flatten() }
  };
}
const feedback = { ...parseResult.data, timestamp: new Date().toISOString() };
```

---

## P2 — E-mail do atendente exposto em log

**Classificação:** Violação do AGENTS.md | Problema de segurança
**Localização:** `console.log('Feedback recebido:', JSON.stringify(feedback));`
**O que está errado:** O objeto logado inclui `attendantEmail`, um dado pessoal. O AGENTS.md proíbe explicitamente logar e-mail ou nome.
**Por que é um problema real:** Logs normalmente vão para sistemas de agregação (Application Insights, Log Analytics) com retenção longa e acesso mais amplo que o banco de dados. Vazar e-mails ali é um risco de privacidade/compliance (LGPD) e amplia desnecessariamente a superfície de exposição de PII.

**Correção proposta:**
```typescript
logger.info(
  { queryId: feedback.queryId, rating: feedback.rating },
  'Feedback recebido'
);
// nunca incluir attendantEmail, comment (pode conter PII) ou outros dados pessoais no log
```

---

## P3 — Endpoint sem controle de autenticação/autorização

**Classificação:** Problema de segurança
**Localização:** `app.http('feedback', { methods: ['POST'], handler: feedbackHandler });`
**O que está errado:** Não há `authLevel` definido, nem qualquer verificação de identidade/autorização dentro do handler.
**Por que é um problema real:** Dependendo da configuração padrão do runtime, isso pode deixar o endpoint acessível publicamente. Sem autenticação, qualquer pessoa pode gravar documentos arbitrários no Cosmos DB (spam, poluição de dados, custo de RU indevido), e não há como saber quem realmente enviou o feedback.

**Correção proposta:**
```typescript
app.http('feedback', {
  methods: ['POST'],
  authLevel: 'function', // ou integrar com Azure AD / validação de token conforme política de acesso do projeto
  handler: feedbackHandler
});
```

---

## P4 — Uso de `console.log` em vez de pino

**Classificação:** Violação do AGENTS.md
**Localização:** `console.log('Feedback recebido:', JSON.stringify(feedback));`
**O que está errado:** O AGENTS.md exige pino para logging; `console.log` nunca deve ser usado.
**Por que é um problema real:** Além de violar a convenção, `console.log` não se integra ao pipeline estruturado de logs do projeto (níveis, correlação de request, formatação JSON consistente para ingestão em ferramentas de observabilidade). Em produção isso significa perda de contexto e dificuldade de correlacionar esse evento com outros logs do serviço.

**Correção proposta:**
```typescript
import { logger } from '../../shared/logger'; // instância pino do projeto

logger.info({ queryId: feedback.queryId }, 'Feedback recebido');
```

---

## P5 — `require` dinâmico em vez de import estático

**Classificação:** Violação do AGENTS.md | Bug potencial
**Localização:** `const { CosmosClient } = require('@azure/cosmos');`
**O que está errado:** O AGENTS.md proíbe `require` dinâmico; imports devem ser estáticos no topo do arquivo.
**Por que é um problema real:** Além da violação direta da convenção, Azure Functions costuma ser empacotado com bundlers (esbuild/webpack) para deploy; `require` dinâmico dentro de uma função pode não ser resolvido corretamente pelo bundler, causando falha em runtime só em produção (e não localmente), um bug difícil de detectar em CI.

**Correção proposta:**
```typescript
import { CosmosClient } from '@azure/cosmos';
```

---

## P6 — Cast `as any` sem tipagem real

**Classificação:** Violação do AGENTS.md | Bug potencial
**Localização:** `const body = await request.json() as any;`
**O que está errado:** O projeto roda em `strict mode`, e `as any` anula completamente a verificação de tipos — o TypeScript não vai pegar nenhum erro de acesso a propriedade inexistente ou tipo incorreto.
**Por que é um problema real:** Com `any`, erros que o compilador deveria capturar em tempo de build (ex.: `body.rating` sendo `string` em vez de `number`) só aparecem em produção. Combinado com a ausência de Zod (P1), não há nenhuma camada de segurança de tipos entre o input externo e o banco de dados.

**Correção proposta:**
```typescript
type Feedback = z.infer<typeof feedbackSchema>; // tipo derivado do schema, sem `any`
```

---

## P7 — Ausência de tratamento de erros

**Classificação:** Bug potencial
**Localização:** Corpo inteiro da função `feedbackHandler`
**O que está errado:** Não há `try/catch` em nenhum ponto. `request.json()` pode lançar se o body não for JSON válido; `container.items.create()` pode falhar por throttling (429), conexão instável, ou connection string inválida.
**Por que é um problema real:** Uma exceção não tratada pode resultar em erro 500 genérico do runtime do Azure Functions, potencialmente expondo stack trace ao cliente, e sem nenhum log estruturado do que aconteceu — dificultando o diagnóstico em produção.

**Correção proposta:**
```typescript
export async function feedbackHandler(request: HttpRequest): Promise<HttpResponseInit> {
  try {
    // ... validação e persistência
    return { status: 200, jsonBody: { success: true } };
  } catch (error) {
    logger.error({ err: error }, 'Falha ao processar feedback');
    return { status: 500, jsonBody: { error: 'Erro interno ao processar feedback' } };
  }
}
```

---

## P8 — `CosmosClient` instanciado a cada requisição

**Classificação:** Bug potencial
**Localização:** `const client = new CosmosClient(...)` dentro do handler
**O que está errado:** Um novo client (e, por baixo dos panos, novas conexões) é criado em toda invocação da function.
**Por que é um problema real:** Sob carga, isso gera overhead de conexão desnecessário, aumenta latência por requisição e pode levar a exaustão de conexões/handles no processo da Function App. O padrão recomendado é instanciar o client uma única vez, fora do handler (escopo do módulo), e reutilizá-lo entre invocações (aproveitando o warm start).

**Correção proposta:**
```typescript
import { CosmosClient } from '@azure/cosmos';

// instanciado uma única vez, no carregamento do módulo
const cosmosClient = new CosmosClient(process.env.COSMOS_CONNECTION_STRING!);
const container = cosmosClient.database('novatech').container('feedbacks');

export async function feedbackHandler(request: HttpRequest): Promise<HttpResponseInit> {
  // reutiliza "container" já instanciado
}
```

---

## P9 — Variável de ambiente não validada

**Classificação:** Bug potencial
**Localização:** `process.env.COSMOS_CONNECTION_STRING`
**O que está errado:** O valor é usado diretamente sem checar se existe.
**Por que é um problema real:** Se a variável não estiver configurada (erro de deploy, ambiente novo, rotação de secret falhou), o erro só aparece como uma exceção genérica do SDK do Cosmos em runtime, sem mensagem clara sobre a causa raiz.

**Correção proposta:**
```typescript
const connectionString = process.env.COSMOS_CONNECTION_STRING;
if (!connectionString) {
  throw new Error('COSMOS_CONNECTION_STRING não configurada');
}
const cosmosClient = new CosmosClient(connectionString);
```

---

## P10 — Arquivo fora da localização/nome esperados

**Classificação:** Violação do AGENTS.md
**Localização:** Arquivo inteiro (`feedback-handler.ts`)
**O que está errado:** O arquivo deveria estar em `/src/functions/feedback/handler.ts`, mas foi gerado como `feedback-handler.ts`, provavelmente na raiz ou em outro diretório.
**Por que é um problema real:** Quebra a convenção de organização do projeto, dificultando localizar o handler por convenção de pastas e podendo confundir ferramentas de build/roteamento que dependem da estrutura padrão de `src/functions/<nome>/handler.ts`.

**Correção proposta:**
```bash
mv feedback-handler.ts src/functions/feedback/handler.ts
```

---

## P11 — Resposta HTTP não padronizada

**Classificação:** Bug potencial
**Localização:** `return { status: 200, body: 'OK' };`
**O que está errado:** Retorna texto puro em vez de um payload JSON estruturado, e não há nenhum status de erro diferenciado (400 para validação, 500 para falha interna) — que aliás só existirão depois de corrigir P1 e P7.
**Por que é um problema real:** Clientes (frontend, outros serviços) normalmente esperam um contrato JSON consistente para sucesso e erro. Retornar texto plano dificulta a integração e a evolução da API (ex.: adicionar um `id` do documento criado).

**Correção proposta:**
```typescript
const created = await container.items.create(feedback);
return { status: 200, jsonBody: { success: true, id: created.resource?.id } };
```

---

## Tabela-resumo

| # | Problema | Classificação | Severidade |
|---|----------|----------------|------------|
| P1 | Nenhuma validação de input (sem Zod) | Violação do AGENTS.md / Segurança | **Crítico** |
| P2 | E-mail do atendente exposto em log | Violação do AGENTS.md / Segurança | **Crítico** |
| P3 | Endpoint sem autenticação/autorização | Segurança | **Crítico** |
| P4 | `console.log` em vez de pino | Violação do AGENTS.md | Alto |
| P5 | `require` dinâmico em vez de import estático | Violação do AGENTS.md / Bug potencial | Alto |
| P6 | Cast `as any` sem tipagem real | Violação do AGENTS.md / Bug potencial | Alto |
| P7 | Ausência de tratamento de erros | Bug potencial | Alto |
| P8 | `CosmosClient` recriado a cada requisição | Bug potencial | Médio |
| P9 | Variável de ambiente não validada | Bug potencial | Médio |
| P10 | Arquivo fora da localização/nome esperados | Violação do AGENTS.md | Baixo |
| P11 | Resposta HTTP não padronizada | Bug potencial | Baixo |

## Veredito

Este PR **não deve ser mergeado como está**. P1, P2 e P3 são bloqueadores — envolvem segurança e conformidade (LGPD), não apenas estilo. Recomenda-se devolver ao autor/Copilot com este review e solicitar uma nova iteração aplicando o schema Zod, o logger pino do projeto (sem PII) e o `authLevel` explícito antes de reavaliar.
