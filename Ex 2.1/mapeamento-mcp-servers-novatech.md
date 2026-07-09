# Mapeamento de MCP Servers — NovaTech Assistant

> **Fase do projeto:** prototipagem local. Todos os serviços corporativos da NovaTech
> (SharePoint/Confluence, Azure AI Search, Azure DevOps, GitHub) são simulados por
> **MCP reference servers** gratuitos, rodando sobre pastas locais do repositório
> `novatech-assistant`. Azure OpenAI é o único serviço que **não** passa por MCP —
> ver justificativa na Seção 1, item 3.
>
> Reference servers considerados: `@modelcontextprotocol/server-filesystem`,
> `@modelcontextprotocol/server-git`, `@modelcontextprotocol/server-memory`,
> `@modelcontextprotocol/server-everything`.

---

## Seção 1 — Tabela de Mapeamento (Serviço Corporativo → MCP Server Local)

| # | Serviço corporativo | Equivalente local (MCP server) | Aponta para | Existe publicamente? | Quem consome |
|---|---|---|---|---|---|
| 1 | **GitHub** (`novatech-assistant`) | `git` — instância única `git-repo` | Raiz do repositório (`repo_path = .`) | ✅ Sim — reference server oficial | Dev (IDE/Claude Code), Copilot (leitura de diffs para revisão), pipeline de CI (log/status para changelog) |
| 2 | **Azure AI Search** | `filesystem` — instâncias `fs-corpus-read` / `fs-corpus-write` | `./data/retrieval-corpus/` | ⚠️ Parcial — o *acesso a arquivo* existe (filesystem), mas a **busca vetorial/semântica não**; isso é uma limitação intencional desta fase (ver nota abaixo) | `pipeline-ingestao` (escreve chunks), `query-endpoint` (lê chunks apenas para depuração/inspeção manual) |
| 3 | **Azure OpenAI** | **Nenhum** — chamada direta via SDK/API pela aplicação | N/A | N/A | `query-endpoint`, `teams-bot` (chamam o endpoint Azure OpenAI diretamente via HTTP) |
| 4 | **Azure DevOps** | `filesystem` — instância `fs-specs` (proxy parcial) | `./specs/` | ⚠️ Parcial — specs em Markdown ficam acessíveis via filesystem; **boards, work items e sprints não têm equivalente em reference server** e precisariam de um server customizado futuro | Dev, Copilot (grounding em specs SDD), pipeline de CI (checagem de specs) |
| 5 | **Confluence NovaTech** | `filesystem` — instância `fs-docs-novatech` | `./docs/novatech/` | ✅ Sim — reference server oficial | `query-endpoint` (grounding de respostas), `teams-bot` (citação de fontes), Dev (validação de conteúdo) |
| 6 | *(adicional)* **memory** | `memory` | Grafo próprio em `./.mcp/memory/novatech-graph.json` (via env `MEMORY_FILE_PATH`) | ✅ Sim | Dev, agentes de sessão longa (ex.: agente de triagem que precisa lembrar decisões de contexto entre interações) |
| 7 | *(adicional)* **everything** | `everything` | Não aponta para dados do projeto — é um server de teste isolado | ✅ Sim | Exclusivamente Dev, em sandbox de onboarding/validação de cliente MCP |

### Notas arquiteturais sobre os casos não triviais

**Item 3 — Por que Azure OpenAI não é um MCP server**
MCP padroniza como um modelo **consome contexto e ferramentas externas** (tools/resources/prompts). Azure OpenAI, no papel do assistente NovaTech, **é o próprio motor de geração** — não uma fonte de contexto para um agente, mas o agente em si (ou o serviço que o `query-endpoint`/`teams-bot` chama para gerar a resposta final após a recuperação de contexto). Modelar a geração como uma "tool" MCP criaria uma dependência circular estranha (um LLM chamando outro LLM como ferramenta de si mesmo) sem benefício real, já que não há dado read-only ou ação de terceiro a expor. Por isso a aplicação chama a API do Azure OpenAI **diretamente via SDK/HTTP**, e o papel do MCP se limita a alimentar o *contexto* que entra no prompt (specs, corpus, docs) antes dessa chamada.

**Item 2 — Limite do `filesystem` como substituto do Azure AI Search**
O server `filesystem` dá acesso a arquivo (ler, listar, buscar por padrão de nome/glob), mas **não implementa embeddings nem similaridade vetorial**. Para esta fase, isso é aceitável porque o objetivo é simular a *estrutura de pastas* do corpus (`./data/retrieval-corpus/`) para desenvolvimento e testes de integração do `pipeline-ingestao` e do `query-endpoint`. A busca semântica real continuará sendo responsabilidade do código da aplicação (`./src/services/retrieval`, por exemplo), que futuramente apontará para o Azure AI Search real. Não é recomendado tentar "forçar" o filesystem a fazer o papel de índice vetorial.

**Item 4 — Por que Azure DevOps é só parcialmente coberto**
Nenhum reference server gratuito modela boards/work items/sprints. A cobertura possível nesta fase é o **conteúdo dos artefatos** (as specs SDD dos 5 módulos, versionadas como Markdown em `./specs/`), via `filesystem`. Tracking de tarefas, estados de sprint e vínculos entre work items ficam fora do escopo do MCP local; se isso for necessário para os agentes, será preciso construir um server customizado (candidato natural para uma fase futura do projeto).

---

## Seção 2 — Detalhamento por MCP Server

### `filesystem` (`@modelcontextprotocol/server-filesystem`)

**Tools expostos** (mesmo conjunto em todas as instâncias — a diferença entre instâncias está em **quais diretórios** cada uma recebe, não em quais tools ela registra):

| Tool | Tipo | Descrição |
|---|---|---|
| `read_text_file` | leitura | Lê arquivo como texto (suporta `head`/`tail`) |
| `read_media_file` | leitura | Lê imagem/áudio/binário como base64 |
| `read_multiple_files` | leitura | Lê vários arquivos de uma vez; falhas individuais não interrompem o lote |
| `list_directory` / `list_directory_with_sizes` | leitura | Lista conteúdo de um diretório |
| `directory_tree` | leitura | Árvore recursiva em JSON |
| `search_files` | leitura | Busca recursiva por padrão glob |
| `get_file_info` | leitura | Metadados (tamanho, datas, permissões) |
| `list_allowed_directories` | leitura | Lista os diretórios permitidos nesta instância |
| `write_file` | escrita | Cria/sobrescreve arquivo |
| `edit_file` | escrita | Edição seletiva por *pattern matching*, com modo `dryRun` |
| `create_directory` | escrita | Cria diretório |
| `move_file` | escrita | Move/renomeia (falha se destino existir) |

**Resources expostos:** nenhum nativamente. O server de filesystem opera **inteiramente via tools** — não há um resource MCP assinável para "o conteúdo da pasta X". Isso é uma limitação relevante: um agente que preferisse *assinar* mudanças em `./docs/novatech/` (via `resources/subscribe`) precisará, em vez disso, chamar `directory_tree`/`list_directory_with_sizes` periodicamente ou o pipeline precisa notificar por fora do MCP.

**Prompts:** nenhum.

**Justificativa de inclusão:** é o único reference server que cobre acesso a documentos e dados tabulares locais — cobre 3 dos 5 serviços mapeados (Confluence, corpus de retrieval, specs do DevOps). Por isso, ao contrário dos outros servers, ele é instanciado **múltiplas vezes** com escopos diferentes (ver Seção 3), em vez de uma única instância genérica apontando para a raiz do projeto.

---

### `git` (`@modelcontextprotocol/server-git`)

**Tools expostos:**

| Tool | Tipo | Descrição |
|---|---|---|
| `git_status` | leitura | Status do working tree |
| `git_diff_unstaged` | leitura | Diff de mudanças não staged |
| `git_diff_staged` | leitura | Diff de mudanças staged |
| `git_diff` | leitura | Diff entre branches/commits |
| `git_log` | leitura | Histórico de commits (com filtro de data) |
| `git_show` | leitura | Conteúdo de um commit específico |
| `git_branch` | leitura | Lista branches locais/remotas |
| `git_add` | escrita | Adiciona arquivos à staging area |
| `git_commit` | escrita | Registra commit |
| `git_reset` | escrita | Remove tudo da staging area |
| `git_create_branch` | escrita | Cria branch |
| `git_checkout` | escrita | Troca de branch |
| `git_init` | escrita | Inicializa repositório |

**Observação importante:** o server **não possui** tools `git_push`, `git_pull` ou `git_clone`. Ou seja, nenhum agente MCP consegue sincronizar com o GitHub remoto por conta própria — qualquer push/pull continua exigindo ação humana fora do protocolo (linha de comando, IDE, ou pipeline de CI configurado separadamente). Isso funciona como uma rede de segurança adicional além das permissões que definirmos.

**Resources expostos:** nenhum — todo acesso a estado do repositório é via tools.

**Prompts:** nenhum.

**Justificativa de inclusão:** cobre o item 1 do mapeamento (GitHub). Permite que agentes (Copilot, pipeline) façam *grounding* em decisões de código — "por que este arquivo mudou", "o que foi comitado na última sprint" — sem dar acesso irrestrito de escrita ao histórico do projeto.

---

### `memory` (`@modelcontextprotocol/server-memory`)

**Tools expostos:**

| Tool | Descrição |
|---|---|
| `create_entities` | Cria entidades no grafo (nome, tipo, observações) |
| `create_relations` | Cria relações direcionadas entre entidades (voz ativa) |
| `add_observations` | Adiciona observações a entidades existentes |
| `delete_entities` | Remove entidades e relações associadas (cascata) |
| `delete_observations` | Remove observações específicas |
| `delete_relations` | Remove relações específicas |
| `read_graph` | Lê o grafo completo |
| `search_nodes` | Busca por nome/tipo/conteúdo de observação |
| `open_nodes` | Recupera nós específicos por nome |

**Resources expostos:** `knowledge-graph` (`memory://knowledge-graph`) — o grafo completo como resource MCP, MIME `application/json`. As tools de mutação emitem `notifications/resources/updated` para esse URI, então clientes assinantes recebem o grafo atualizado sem precisar chamar `read_graph` de novo.

**Prompts:** nenhum.

**Justificativa de inclusão:** dá aos agentes memória persistente entre sessões — por exemplo, o `teams-bot` pode registrar que "o atendente João já perguntou sobre SLA de entrega internacional 3 vezes esta semana" ou o agente de ingestão pode guardar decisões de mapeamento de metadados (ex.: "PDFs da pasta `Contratos/` sempre usam o campo `cliente_id` como chave"). Sem isso, cada sessão do agente começaria do zero.

---

### `everything` (`@modelcontextprotocol/server-everything`)

**Tools expostos (subconjunto relevante para o projeto):** `echo`, `get-sum`, `get-env`, `get-tiny-image`, `get-annotated-message`, `trigger-long-running-operation`, `get-resource-reference`, `get-resource-links` — exercitam, respectivamente, entrada/saída simples, cálculo, variáveis de ambiente, conteúdo de imagem, anotações de prioridade/audiência, operações longas com `notifications/progress`, e referências a resources.

**Resources expostos:** resources dinâmicos de texto e blob (`demo://resource/dynamic/text/{index}`, `demo://resource/dynamic/blob/{index}`) e documentos estáticos de exemplo (`demo://resource/static/document/<arquivo>`).

**Prompts:** `simple-prompt` (sem argumentos), `args-prompt` (argumentos `city`/`state`), `completable-prompt` (demonstra autocompletar de argumentos), `resource-prompt` (embute um resource dinâmico na mensagem).

**Justificativa de inclusão:** não serve para nenhum dado real da NovaTech. Sua função é **validar a implementação do cliente MCP** antes de conectá-lo a servers de produção — por exemplo, confirmar que o cliente do `teams-bot` sabe lidar com `resources/subscribe`, `sampling/createMessage` e progress notifications antes de apontá-lo para o `filesystem`/`git` reais. Uso recomendado: só durante desenvolvimento/onboarding, nunca em ambiente que atenda usuário final.

---

## Seção 3 — Permissões Mínimas (Princípio de Least Privilege)

**Nota de enforcement:** o binário `@modelcontextprotocol/server-filesystem` expõe o **mesmo conjunto de tools** (leitura e escrita) para qualquer diretório passado como argumento — ele não tem uma flag nativa de "somente leitura por pasta". Read-only real, portanto, precisa ser garantido por uma de duas formas (idealmente as duas juntas):
1. **Mount read-only no nível do SO/Docker** (`--mount type=bind,src=...,dst=...,ro`), que bloqueia a escrita mesmo que o agente chame `write_file`;
2. **Allow-list de tools no cliente MCP** (a maioria dos clientes MCP, incluindo Claude Code, permite habilitar/desabilitar tools específicos por servidor conectado), removendo `write_file`/`edit_file`/`create_directory`/`move_file` da lista de tools visíveis ao agente.

Por isso, sempre que a tabela abaixo diz "somente leitura", a recomendação é aplicar **ambas** as camadas.

| Server | Pasta/Escopo | Operações permitidas | Operações bloqueadas | Justificativa |
|---|---|---|---|---|
| `filesystem` (`fs-docs-novatech`) | `./docs/novatech/` | `read_text_file`, `read_multiple_files`, `list_directory`, `list_directory_with_sizes`, `directory_tree`, `search_files`, `get_file_info`, `list_allowed_directories` | `write_file`, `edit_file`, `create_directory`, `move_file` (mount `ro` + fora da allow-list) | Espelha o Confluence real: fonte de verdade de negócio, read-only. Nenhum agente deve alterar documentação institucional. |
| `filesystem` (`fs-specs`) | `./specs/` | Mesmo conjunto de leitura acima | Todas as tools de escrita | Specs SDD são artefatos de decisão arquitetural; só devem mudar via PR revisado por humano, nunca por escrita autônoma de agente. |
| `filesystem` (`fs-corpus-read`) | `./data/retrieval-corpus/` | Mesmo conjunto de leitura acima | Todas as tools de escrita | Usado pelo `query-endpoint` só para inspeção/depuração de chunks recuperados — consultas nunca devem mutar o índice. |
| `filesystem` (`fs-corpus-write`) | `./data/retrieval-corpus/` | Conjunto completo (leitura + `write_file`, `edit_file`, `create_directory`, `move_file`) | Nenhuma tool bloqueada — mas a instância **só é conectada pelo agente `pipeline-ingestao`**, nunca por `query-endpoint`, `teams-bot` ou `painel-web` | Isolar a única instância com escrita real garante que apenas o processo de ingestão popule/atualize o corpus; agentes de consulta continuam presos à instância `-read`. |
| `filesystem` (`fs-skills`) | `./skills/` | Mesmo conjunto de leitura acima | Todas as tools de escrita | Skills de contexto (`foundation`, `domain`, `artifact`) são curadas pela equipe; bloquear escrita evita que um agente reescreva suas próprias instruções sem revisão ("prompt self-modification" descontrolada). |
| `git` | Raiz do repositório (`repo_path = .`) | Para agentes de consulta/pipeline: `git_status`, `git_diff`, `git_diff_staged`, `git_diff_unstaged`, `git_log`, `git_show`, `git_branch`. Para a sessão do Dev: todas as tools, incluindo escrita. | Para agentes de consulta/pipeline: `git_add`, `git_commit`, `git_reset`, `git_create_branch`, `git_checkout`, `git_init` (removidas da allow-list do cliente MCP). Nenhum agente tem `push`/`pull` — essas tools **não existem** no server. | Permite qualquer agente auditar histórico e diffs para grounding ("este chunk mudou porque tal PR alterou o PDF de origem"), sem risco de reescrever histórico, criar branches ou comitar sem revisão humana. |
| `memory` | Arquivo dedicado `./.mcp/memory/novatech-graph.json` (via env `MEMORY_FILE_PATH`) — **não** o `memory.json` default global do pacote | `create_entities`, `create_relations`, `add_observations`, `read_graph`, `search_nodes`, `open_nodes` | `delete_entities`, `delete_relations`, `delete_observations` — reservadas para manutenção manual do Dev | Escopar via `MEMORY_FILE_PATH` evita que o grafo do NovaTech se misture com o de outros projetos DB1 no mesmo host. Bloquear exclusão em agentes de produção evita que um agente apague contexto acumulado por engano ou por instrução maliciosa em um documento ingerido. |
| `everything` | Nenhum dado do projeto (server roda sem argumentos de diretório) | Todas as tools — mas **apenas quando conectado pela sessão local do Dev** | Conexão a partir de qualquer agente de produção (`teams-bot`, `query-endpoint`, `pipeline-ingestao`, `painel-web`) — este server **nunca** deve aparecer no `mcp.json` usado em runtime de produção | Serve só para validar que o cliente MCP implementa corretamente prompts/resources/sampling antes de trocá-lo por servers reais. Atenção extra: a tool `get-env` devolve **todas** as variáveis de ambiente do processo — um risco real de exposição de segredos (chaves do Azure, tokens) se este server for exposto fora de sandbox. |

---

## Seção 4 — Análise de Riscos de Segurança — MCP Servers

> Os dois riscos abaixo são rastreáveis diretamente à configuração definida nas
> Seções 1 e 3: o primeiro decorre de `fs-docs-novatech` expor `./docs/novatech/`
> como uma árvore única e indiferenciada; o segundo decorre da combinação entre o
> escopo de `memory` (`./.mcp/memory/novatech-graph.json`, dentro do working tree
> do repositório) e o fato de o histórico do `git` ser imutável por padrão.

### Risco 1 — Contaminação cruzada de condições comerciais entre clientes via retrieval não segregado

**Server afetado:** `filesystem` (instância `fs-docs-novatech`, que alimenta `fs-corpus-write`/`fs-corpus-read` via `pipeline-ingestao`)

**Cenário concreto:**
`./docs/novatech/` contém, lado a lado, tabelas de frete e SLAs negociados individualmente por cliente (ex.: `Cliente_ACME_SLA.pdf`, `Cliente_Riofort_Tabela_Frete.pdf`). A configuração atual do `fs-docs-novatech` (Seção 3) trata essa pasta como uma **única árvore homogênea** — não há segmentação por cliente no nível do MCP server nem metadado de "dono" do documento sendo respeitado no momento do retrieval.

Passo a passo do incidente:
1. Um atendente da NovaTech abre, via `teams-bot`, um chamado sobre prazo de entrega do **Cliente A**.
2. `teams-bot` chama `query-endpoint`, que faz retrieval semântico sobre `./data/retrieval-corpus/` (populado a partir de `fs-docs-novatech`).
3. Por similaridade textual (ex.: ambos os documentos mencionam "frete internacional — região Sul"), o retrieval traz, junto ao SLA do Cliente A, um chunk da **tabela de frete negociada especificamente com o Cliente B** — um concorrente direto do Cliente A no mesmo segmento de distribuição.
4. Esse chunk entra no prompt de contexto que a aplicação monta e envia **diretamente** (Seção 1, item 3) para o Azure OpenAI (ou outro LLM cloud configurado, como Claude API/GPT-4).
5. O modelo, ao gerar a resposta final, pode parafrasear ou citar parcialmente a condição comercial do Cliente B (ex.: "outros contratos da região praticam desconto de X% sobre a tabela padrão").
6. O atendente, sem saber que aquele dado pertence a outro cliente, repassa a informação — ainda que parcialmente — na conversa com o Cliente A.

**Impacto:**
- **Contratual:** a maioria dos contratos de frete/logística tem cláusula de confidencialidade sobre condições comerciais negociadas; vazar a tabela do Cliente B para o Cliente A é quebra de contrato por parte da NovaTech (e, por extensão, risco reputacional para a DB1 como fornecedora do assistente).
- **Legal/concorrencial:** se o Cliente A e o Cliente B forem concorrentes no mesmo mercado, a exposição de descontos negociados pode configurar vazamento de informação competitivamente sensível, com risco de ação judicial.
- **Operacional:** perda de confiança no assistente por parte dos atendentes, que passam a desconfiar de qualquer resposta envolvendo dados comerciais — reduzindo a adoção da ferramenta.

**Mitigação proposta:**
1. **Reestruturar `./docs/novatech/` por cliente antes da ingestão:** mover documentos comerciais para subpastas `./docs/novatech/clientes/<cliente_id>/`, mantendo `./docs/novatech/geral/` só para políticas não vinculadas a um cliente específico (ex.: política de devolução padrão).
2. **Escopar o `fs-docs-novatech` dinamicamente por sessão via MCP Roots**, em vez de uma lista fixa de diretórios no `mcp.json`: o filesystem server já suporta receber `roots/list` do cliente MCP e substituir os diretórios permitidos em runtime (isso está documentado no próprio reference server). O backend do `teams-bot`/`query-endpoint`, ao abrir a sessão MCP para atender um chamado do Cliente A, envia como Root **apenas** `./docs/novatech/clientes/cliente-a/` (+ `./docs/novatech/geral/`). Isso torna fisicamente impossível o agente ler a pasta do Cliente B nessa sessão, independentemente do que o LLM "decida" buscar.
3. **Adicionar filtro de metadado `cliente_id` na etapa de geração**, como camada redundante: o `pipeline-ingestao` já tagueia cada chunk com `cliente_id` (prática mencionada na Seção 2). Antes de montar o prompt final para o Azure OpenAI, o código do `query-endpoint` deve **descartar** qualquer chunk cujo `cliente_id` seja diferente do `cliente_id` do chamado em atendimento — mesmo que o Root não tenha bloqueado o acesso por algum motivo (ex.: bug de configuração).
4. **Testar a segregação com um caso de teste automatizado** no pipeline de CI: uma consulta simulada sobre o Cliente A não pode retornar nenhum chunk cujo `cliente_id` seja diferente de "cliente-a" — isso vira um gate de merge, não só uma recomendação.

---

### Risco 2 — Exposição permanente de dados comerciais sensíveis via memória local versionada acidentalmente no Git

**Server afetado:** `memory` (persistência primária do risco) combinado com `git` (o que transforma um incidente reversível em irreversível)

**Cenário concreto:**
Hoje o `memory` está configurado (Seção 3) para gravar em `./.mcp/memory/novatech-graph.json` — um caminho **dentro do working tree** do repositório `novatech-assistant`. Suponha que o agente de triagem do `teams-bot`, ao usar `add_observations` para lembrar contexto entre interações, registre algo como:

> entidade `Cliente_ACME`, observação: *"Atendente Ana negociou verbalmente 15% de desconto sobre a tabela de frete padrão para o Cliente ACME em 03/07; aguardando formalização."*

Esse dado — um percentual de desconto comercial negociado e ainda não formalizado — fica gravado em texto puro em `./.mcp/memory/novatech-graph.json`, na máquina local de um desenvolvedor da DB1 (ex.: "Dev X") que está testando o `teams-bot` localmente.

1. Dev X, ao final do dia, roda um `git add .` de rotina (comando comum para capturar mudanças de código) antes de comitar uma feature não relacionada.
2. Como `./.mcp/memory/` está dentro da árvore do repositório e **não consta em `.gitignore`**, o arquivo `novatech-graph.json` — com o desconto negociado do Cliente ACME — entra no commit e é enviado (`git push`, fora do MCP, via linha de comando normal) ao repositório remoto no GitHub da DB1.
3. Alguém percebe o problema dias depois e remove o arquivo em um novo commit ("fix: remover memory.json do repo").
4. **O dado continua acessível para sempre**: como o `git` reference server (e o Git em geral) preserva histórico imutável por padrão, qualquer pessoa com acesso de leitura ao repositório — incluindo futuros colaboradores da DB1, um agente com a tool `git_show`/`git_log` apontando para aquele commit antigo, ou um auditor externo — consegue recuperar o desconto negociado do Cliente ACME simplesmente inspecionando o histórico, mesmo que o arquivo "não exista mais" no HEAD atual.

**Impacto:**
- **Contratual:** condição comercial negociada e ainda não formalizada (15% de desconto) exposta antes mesmo de virar cláusula contratual — se o Cliente ACME descobrir que esse dado circulou fora do canal formal, há risco de reabertura de negociação em desvantagem para a NovaTech.
- **Operacional:** se o repositório GitHub da DB1 tiver colaboradores externos ao time NovaTech (comum em squads compartilhados), o dado fica exposto a pessoas sem necessidade de conhecê-lo (violação de *need-to-know*).
- **Legal:** dependendo do que mais estiver nas `observations` do grafo (ex.: nome do atendente, nome de contato do cliente, e-mail), pode configurar tratamento inadequado de dado pessoal sob a LGPD, já que o dado passou a residir em um repositório de código sem os controles de acesso e retenção aplicáveis a dado de negócio/pessoal.

**Mitigação proposta:**
1. **Mover o `MEMORY_FILE_PATH` para fora do working tree do repositório**, ex.: `~/.novatech-assistant/memory/novatech-graph.json` (diretório home do desenvolvedor, fora de qualquer pasta rastreada pelo Git) em vez de `./.mcp/memory/...`. Isso é uma mudança de uma linha na variável de ambiente do server `memory` no `mcp.json`/`.env` de cada máquina — elimina a possibilidade de `git add .` capturar o arquivo, porque o Git nunca vê esse caminho.
2. **Adicionar um pre-commit hook** (ex.: via `husky` + `lint-staged`, já que o projeto é TypeScript) que bloqueia qualquer commit contendo caminhos que casem com o padrão `.mcp/memory/*.json` ou `*novatech-graph.json` — camada de defesa redundante caso alguém reconfigure o `MEMORY_FILE_PATH` de volta para dentro do repo por engano.
3. **Restringir o que pode ser gravado como `observation`**: atualizar a skill de contexto do agente de triagem (`./skills/domain/`) para instruir explicitamente que valores comerciais brutos (percentuais de desconto, valores de frete, condições ainda não formalizadas) **nunca** devem ser passados para `add_observations` — apenas referências abstratas (ex.: "ticket #4521 têm negociação em andamento, ver CRM") que exigem consulta a uma fonte controlada (não ao grafo de memória) para recuperar o valor real.
4. **Higienizar o histórico já existente antes de abrir o repositório para mais colaboradores ou torná-lo menos restrito**: se já houve algum commit com dado sensível, rodar `git filter-repo` (ou BFG Repo-Cleaner) **agora, na fase de prototipagem**, e forçar todos os clones locais a se re-sincronizarem. Depois que o repositório for amplamente clonado/forkado, essa limpeza se torna praticamente inviável — por isso a janela de correção é curta e deve ser tratada como bloqueante, não como *nice-to-have*.

---

## Anexo — Esqueleto de referência para `./.mcp/mcp.json`

Ilustra como as instâncias acima poderiam ser declaradas (ajustar caminhos absolutos e mecanismo de enforcement read-only conforme o runtime escolhido — Docker ou npx + allow-list do cliente):

```jsonc
{
  "mcpServers": {
    "fs-docs-novatech": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/abs/path/novatech-assistant/docs/novatech"],
      "_permissoes": "somente-leitura via allow-list do cliente (bloquear write_file, edit_file, create_directory, move_file)"
    },
    "fs-specs": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/abs/path/novatech-assistant/specs"],
      "_permissoes": "somente-leitura"
    },
    "fs-corpus-read": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/abs/path/novatech-assistant/data/retrieval-corpus"],
      "_permissoes": "somente-leitura — usado por query-endpoint"
    },
    "fs-corpus-write": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/abs/path/novatech-assistant/data/retrieval-corpus"],
      "_permissoes": "leitura+escrita — conectar apenas no agente pipeline-ingestao"
    },
    "fs-skills": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/abs/path/novatech-assistant/skills"],
      "_permissoes": "somente-leitura"
    },
    "git-repo": {
      "command": "npx",
      "args": ["-y", "mcp-server-git", "--repository", "/abs/path/novatech-assistant"],
      "_permissoes": "leitura para todos; escrita (add/commit/branch/checkout) só na sessão do Dev"
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE_PATH": "/abs/path/novatech-assistant/.mcp/memory/novatech-graph.json"
      },
      "_permissoes": "delete_* reservado ao Dev"
    },
    "everything": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-everything"],
      "_permissoes": "somente sandbox local do Dev — nunca em produção"
    }
  }
}
```

> Este `mcp.json` é um esqueleto de referência para discussão da equipe — os campos `_permissoes` são comentários informativos (não fazem parte do schema oficial do MCP) e servem para deixar explícita, ao lado da configuração, a decisão de least privilege tomada na Seção 3.
