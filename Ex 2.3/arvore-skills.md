# Árvore de Skills de IA — novatech-assistant

> Documento de estratégia técnica definindo como as skills (Foundation → Domain →
> Artifact) são criadas, mantidas e consumidas por humanos e agentes de IA
> (GitHub Copilot, Claude) no repositório `novatech-assistant`.

**Nota de escopo:** a estrutura atual cobre as 10 skills já definidas no
repositório, focadas em código (TypeScript, endpoints, testes, UI). Documentação
técnica (ADRs, READMEs) e specs de produto (SDD) são artefatos recorrentes citados
no contexto do projeto, mas ainda não têm skill dedicada — recomenda-se avaliar
`create-adr.md` e `create-product-spec.md` como próximos candidatos, fora do
escopo deste documento.

---

## Seção 1 — Árvore de skills com descrição

### FOUNDATION

#### [FOUNDATION] typescript-conventions.md

- **Nome legível:** Convenções de TypeScript
- **Frase-ativação:** Sempre que criar ou modificar qualquer arquivo `.ts` ou
  `.tsx` no projeto.
- **Propósito:** Ensina o agente a seguir o style guide do projeto — modo
  `strict`, proibição de `any`, convenções de nomenclatura (camelCase para
  funções/variáveis, PascalCase para tipos/componentes), organização de imports,
  e uso de Zod para validação de dados em vez de type assertions manuais. É a
  base sintática sobre a qual todas as outras skills constroem.
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Alta (toda task de código).
- **Skills que depende:** Nenhuma — é a raiz da árvore.

#### [FOUNDATION] error-handling.md

- **Nome legível:** Padrão de Tratamento de Erros
- **Frase-ativação:** Sempre que o código precisar lançar, capturar, propagar ou
  logar um erro — endpoints, integrações externas (Azure AI Search), validações
  de entrada.
- **Propósito:** Define a hierarquia de erros customizados do projeto (ex:
  `AppError`, `ValidationError`, `ExternalServiceError`), o padrão de logging
  estruturado com `pino` (incluindo `correlationId` por request) e o formato
  consistente de resposta HTTP de erro devolvido pelos endpoints Azure
  Functions.
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Alta (toda task de código).
- **Skills que depende:** `typescript-conventions.md`.

#### [FOUNDATION] project-structure.md

- **Nome legível:** Estrutura de Pastas e Módulos
- **Frase-ativação:** Sempre que criar um novo arquivo, módulo, endpoint ou
  componente e precisar decidir onde ele deve viver no repositório.
- **Propósito:** Mapeia a organização de diretórios do monorepo (`src/functions`,
  `src/services`, `src/components`, `src/lib`, `tests/`, `infra/` para Bicep),
  convenções de nomenclatura de arquivos e regras de dependência entre camadas
  (ex: componentes React não importam diretamente o SDK do Azure).
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Alta (toda task de código).
- **Skills que depende:** `typescript-conventions.md`.

---

### DOMAIN

#### [DOMAIN] azure-functions-endpoint.md

- **Nome legível:** Padrões de Endpoint Azure Functions v4
- **Frase-ativação:** Sempre que implementar, revisar ou modificar um endpoint
  HTTP em Azure Functions v4.
- **Propósito:** Ensina o padrão de handler do projeto — registro via
  `app.http`, parsing e validação de request com schemas Zod, aplicação do
  middleware padrão de autenticação/logging, e retorno de `HttpResponseInit`
  consistente. Cobre também quando um novo endpoint exige ajuste no `main.bicep`
  (rotas, app settings).
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Alta (toda task de código que envolve API).
- **Skills que depende:** `typescript-conventions.md`, `error-handling.md`,
  `project-structure.md`.

#### [DOMAIN] azure-ai-search-integration.md

- **Nome legível:** Integração com Azure AI Search (RAG)
- **Frase-ativação:** Sempre que o código precisar consultar, indexar ou
  configurar o índice do Azure AI Search usado no pipeline de retrieval.
- **Propósito:** Define o client wrapper padrão do projeto para o Azure AI
  Search, o formato de query (hybrid search: vetorial + full-text), o
  mapeamento de scores e citações para o formato de resposta do assistente, e a
  política de retry/timeout para chamadas a um serviço externo.
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Média (toda sprint com trabalho em RAG/retrieval).
- **Skills que depende:** `typescript-conventions.md`, `error-handling.md`.

#### [DOMAIN] react-components.md

- **Nome legível:** Padrões de Componentes React (Painel Web)
- **Frase-ativação:** Sempre que criar ou modificar um componente React no
  painel web da NovaTech.
- **Propósito:** Define convenções de tipagem de props, estrutura de arquivo
  (componente + estilos + teste colocalizados), padrão de gerenciamento de
  estado com hooks, acessibilidade básica (labels, foco, aria), e o padrão de
  estados de `loading`/`error`/`empty` ao consumir dados de endpoints RAG.
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Alta (toda task de código que envolve UI).
- **Skills que depende:** `typescript-conventions.md`, `project-structure.md`.

#### [DOMAIN] testing-patterns.md

- **Nome legível:** Padrões de Testes com Vitest
- **Frase-ativação:** Sempre que escrever qualquer teste unitário ou de
  integração no projeto.
- **Propósito:** Define a estrutura de `describe`/`it`, o padrão de
  mocks/fixtures para dependências externas (Azure AI Search, storage), a
  convenção de nomenclatura de arquivos de teste (`*.test.ts`) e o critério
  mínimo de cobertura aceito antes de um PR ser aprovado.
- **Quem cria:** Tech Lead.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Alta (toda task de código gera ao menos um teste).
- **Skills que depende:** `typescript-conventions.md`, `error-handling.md`.

---

### ARTIFACT

#### [ARTIFACT] create-rag-endpoint.md

- **Nome legível:** Receita — Criar Endpoint RAG
- **Frase-ativação:** Ao criar um novo endpoint Azure Functions que segue o
  padrão RAG (recebe pergunta → busca contexto no AI Search → chama o LLM →
  retorna resposta com citações).
- **Propósito:** Receita passo a passo que combina os padrões de domínio em um
  fluxo único: schema Zod de entrada/saída, chamada ao wrapper de Azure AI
  Search, construção do prompt com contexto recuperado, formatação da resposta
  com citações, e geração do teste de integração correspondente.
- **Quem cria:** Dev (quem implementa o padrão repetidamente e captura os
  detalhes práticos).
- **Quem consome:** Dev (humano); Copilot e Claude (agentes) — este é o caso de
  uso principal para geração direta de código pelo agente.
- **Frequência de uso:** Média (recorrente a cada novo endpoint RAG, não em
  toda task).
- **Skills que depende:** `azure-functions-endpoint.md`,
  `azure-ai-search-integration.md`, `error-handling.md`, `testing-patterns.md`.

#### [ARTIFACT] create-integration-test.md

- **Nome legível:** Receita — Criar Teste de Integração de Endpoint
- **Frase-ativação:** Ao criar o teste de integração para um endpoint
  recém-criado ou modificado.
- **Propósito:** Receita para gerar um teste que sobe o handler do endpoint,
  mocka as dependências externas (Azure AI Search, storage), cobre os casos de
  sucesso, erro de validação e falha de dependência externa, seguindo a
  convenção de nomenclatura combinada em `testing-patterns.md`.
- **Quem cria:** Dev.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Média (todo endpoint novo ou alterado gera um teste,
  mas não é toda task).
- **Skills que depende:** `testing-patterns.md`, `azure-functions-endpoint.md`,
  `error-handling.md`.

#### [ARTIFACT] create-react-card.md

- **Nome legível:** Receita — Criar Card de Resposta React
- **Frase-ativação:** Ao criar um novo card ou componente visual que exibe uma
  resposta do assistente RAG ou um formulário de feedback no painel.
- **Propósito:** Receita para gerar o componente completo (componente + estilos
  + teste), seguindo o layout padrão de card do painel (corpo da resposta,
  lista de citações, botões de feedback), com acessibilidade e estados de
  `loading`/erro já embutidos.
- **Quem cria:** Dev.
- **Quem consome:** Dev (humano); Copilot e Claude (agentes).
- **Frequência de uso:** Baixa (ocasional — poucos tipos de card recorrentes no
  painel).
- **Skills que depende:** `react-components.md`, `testing-patterns.md`,
  `project-structure.md`.

---

## Seção 2 — Matriz de criação e consumo

| Skill | Nível | Cria | Revisa | Consome (humano) | Consome (agente) | Freq. |
|---|---|---|---|---|---|---|
| `typescript-conventions.md` | Foundation | Tech Lead | Dev | Dev | Copilot + Claude | Alta |
| `error-handling.md` | Foundation | Tech Lead | Dev | Dev | Copilot + Claude | Alta |
| `project-structure.md` | Foundation | Tech Lead | Dev | Dev | Copilot + Claude | Alta |
| `azure-functions-endpoint.md` | Domain | Tech Lead | Dev | Dev | Copilot + Claude | Alta |
| `azure-ai-search-integration.md` | Domain | Tech Lead | Dev | Dev | Copilot + Claude | Média |
| `react-components.md` | Domain | Tech Lead | Dev | Dev | Copilot + Claude | Alta |
| `testing-patterns.md` | Domain | Tech Lead | Dev | Dev | Copilot + Claude | Alta |
| `create-rag-endpoint.md` | Artifact | Dev | Tech Lead | Dev | Copilot + Claude | Média |
| `create-integration-test.md` | Artifact | Dev | Tech Lead | Dev | Copilot + Claude | Média |
| `create-react-card.md` | Artifact | Dev | Tech Lead | Dev | Copilot + Claude | Baixa |

**Lógica da matriz de revisão:** as skills Foundation e Domain são escritas
top-down pelo Tech Lead (decisões de arquitetura) e revisadas por Dev, que
valida se o padrão é praticável no dia a dia de implementação. As skills
Artifact seguem o caminho inverso — são escritas bottom-up pelo Dev que executa
o padrão repetidamente e sabe onde estão as armadilhas práticas, e revisadas
pelo Tech Lead, que garante aderência às skills de Domain das quais dependem.
Isso evita que a receita de artefato "vaze" um padrão divergente da arquitetura
aprovada.

O Product Specialist não aparece na matriz porque nenhuma das 10 skills atuais
cobre os artefatos que ele produz (`requirements.md`, specs de negócio) — reforça
a lacuna apontada na nota de escopo no início deste documento.

### Ordem de criação recomendada

1. **`typescript-conventions.md`** — raiz da árvore, sem dependências. Precisa
   existir antes de qualquer outra skill fazer referência a tipagem, naming ou
   uso de Zod.
2. **`project-structure.md`** — depende só de `typescript-conventions.md`.
   Precisa vir cedo porque toda skill de Domain e Artifact vai referenciar
   "onde este arquivo deve viver".
3. **`error-handling.md`** — depende de `typescript-conventions.md`. Vem depois
   de `project-structure.md` porque a hierarquia de erros customizados precisa
   de um local definido no repositório para existir.
4. **`testing-patterns.md`** — depende de `typescript-conventions.md` e
   `error-handling.md` (mocks de erro fazem parte do padrão de teste). É
   priorizada entre as skills de Domain porque três das quatro skills de
   Artifact dependem dela.
5. **`azure-functions-endpoint.md`** — depende das três Foundation skills.
   Desbloqueia a skill de RAG e a de teste de integração, então vem antes
   delas.
6. **`azure-ai-search-integration.md`** — depende de `typescript-conventions.md`
   e `error-handling.md`. É a única skill de Domain com uso Médio (não Alto),
   por isso pode vir depois de `azure-functions-endpoint.md`.
7. **`react-components.md`** — depende de `typescript-conventions.md` e
   `project-structure.md`. Não bloqueia nenhuma skill de backend, então pode
   ser escrita em paralelo com o trabalho de RAG, mas precisa existir antes de
   `create-react-card.md`.
8. **`create-integration-test.md`** — depende de `testing-patterns.md` e
   `azure-functions-endpoint.md` (já disponíveis). Vem antes de
   `create-rag-endpoint.md` porque tem menos dependências (não precisa de
   `azure-ai-search-integration.md`) e serve de base para o teste que a receita
   de RAG vai reutilizar.
9. **`create-rag-endpoint.md`** — depende de todas as quatro skills de Domain e
   de `error-handling.md`. É a última das duas primeiras receitas de Artifact
   porque só pode ser escrita quando `azure-ai-search-integration.md` já
   existir.
10. **`create-react-card.md`** — depende de `react-components.md`,
    `testing-patterns.md` e `project-structure.md`, todas já disponíveis neste
    ponto. Fica por último por ser a skill de menor frequência de uso (Baixa) e
    a menos crítica para o fluxo principal de RAG do projeto.
