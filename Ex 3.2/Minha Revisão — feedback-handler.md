# Minha Revisão — feedback-handler.ts

## Problema 1
- **Classificação:** Violação do AGENTS.md;
- **Localização:** "console.log('Feedback recebido:', JSON.stringify(feedback));"
- **O que está errado:** O Objeto "feedback" contém "attendantEmail" e é impresso no console;
- **Por que é um problema:** O AGENTS.md tem uma restrição quanto a isso: "Nunca logar dados pessoais (e-mail, nome)", ou seja, o e-mail sendo impresso vai contra a regra, além de infringir a LGPD.

## Problema 2
- **Classificação:** Violação do AGENTS.md e potencial bug;
- **Localização:** "const body = await request.json() as any;"
- **O que está errado:** Tipagem da constante "body" ser any e não haver nenhuma validação, muito menos utilizando Zod;
- **Por que é um problema:** Não há nenhuma validação do que vem como "body", além da tipagem ter sido completamente inutilizada ao se usar "any". Ademais, isso viola uma das regras impostas no AGENTS.md: "Zod para validação de input", onde Zod não está sendo utilizada, e nenhuma forma de validação está presente.

## Problema 3
- **Classificação:** Violação do AGENTS.md;
- **Localização:** "const { CosmosClient } = require('@azure/cosmos');"
- **O que está errado:** Import dinâmico no meio do código;
- **Por que é um problema:** O AGENTS.md expõe uma regra explícita: "Imports estáticos no topo (nunca require dinâmico)", ou seja, é exigido que tenha imports estáticos, visíveis e previsíveis no topo do arquivo, e não no meio do código.

## Problema 4
- **Classificação:** Violação do AGENTS.md;
- **Localização:** "console.log('Feedback recebido:', JSON.stringify(feedback));"
- **O que está errado:** Uso de "console.log";
- **Por que é um problema:** O AGENTS.md dita uma regra para logar: "pino para logging (nunca console.log)" e o código está, justamente, logando utilizando a única proibição: o console.log.

## Problema 5
- **Classificação:** Potencial bug;
- **Localização:** Função inteira do "feedbackHandler";
- **O que está errado:** Falta de tratamento de erros;
- **Por que é um problema:** Ao deixar o código sem um bloco de try/catch, o código passa a rodar de forma independente e perigosa, pois qualquer erro fará com que a função quebre, podendo destruir a aplicação em tempo de execução, ainda mais por ter conexão com o CosmosDB. Tratamento de erro é vital.