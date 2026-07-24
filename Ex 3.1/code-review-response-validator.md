# Code Review — `response-validator.ts`

## Resumo executivo

O módulo tem uma arquitetura correta (schema → guardrail 1 → guardrail 2 → fallback), boa separação de responsabilidades e comentários que explicam decisões de design — isso facilita muito o review. Mas o **guardrail 2 (carga perigosa + devolução) tem um bypass real e demonstrável**, que é exatamente o guardrail mais sensível do módulo (o que evita afirmar que devolução de carga perigosa é possível). Isso é o achado central desta revisão.

---

### P1 — Schema Zod não é `.strict()`

**Localização:** `StructuredAssistantResponseSchema`

**O que está errado:** o schema usa o modo padrão do Zod (`strip`), que descarta silenciosamente qualquer campo desconhecido no payload de entrada, em vez de rejeitar.

**Por que é um problema real:** este módulo é o *último checkpoint determinístico* antes da resposta chegar ao atendente. Se o pipeline upstream (LLM, parser RAG, etc.) começar a enviar um payload com forma diferente da esperada — por exemplo, por causa de uma migração de campo, um bug de serialização, ou um novo campo adicionado por outro time sem coordenação — o `strip` mode absorve isso silenciosamente. O harness "passa" um objeto que tecnicamente não é mais o que o pipeline pretendia, e ninguém percebe até o problema aparecer em produção de outra forma. Num harness de segurança, drift de contrato deveria **falhar alto e auditável** (cair no `safeParse` → fallback + log), não ser mascarado.

**Correção proposta:**
```typescript
export const StructuredAssistantResponseSchema = z
	.object({
		answer: z.string(),
		source_document: z.string(),
		confidence_score: z.number().min(0).max(1),
	})
	.strict();
```

---

### P2 — Heurística de negação ignora a estrutura da frase (co-ocorrência global, não por cláusula)

**Localização:** `checkDangerousCargoReturnGuardrail`

**O que está errado:** `hasDangerousTopic`/`hasReturnTopic` avaliam o **texto inteiro** da resposta, e a busca por `NEGATION_MARKERS` também é feita no texto inteiro (`normalizedAnswer.includes(marker)`). Não há nenhuma relação entre *onde* a negação aparece e *onde* o par "perigoso + devolução" aparece.

**Por que é um problema real — nos dois sentidos:**

- **Falso negativo (grave, deixa passar conteúdo perigoso):** basta existir uma negação em **qualquer lugar** da resposta, sobre **qualquer assunto**, para "salvar" uma afirmação de permissão em outra parte do texto:
  > "Não podemos garantir o prazo de entrega, mas a devolução de carga perigosa é permitida sem restrições."

  Esse texto contém `nao podem` (marcador de negação) e também afirma explicitamente que a devolução **é permitida** — e o guardrail atual retorna `true` (válido), deixando passar exatamente o que ele existe para bloquear.

- **Falso positivo (bloqueia resposta correta):**
  > "Este pedido não envolve carga perigosa. A devolução de itens padrão pode ser feita em até 7 dias."

  Aqui `perigos` e `devolu` aparecem no texto inteiro (co-ocorrência), mas em frases completamente diferentes e sem relação. Nenhum marcador de negação padrão bate literalmente, então essa resposta — que está **correta** — seria bloqueada e escalada desnecessariamente.

**Sobre os exemplos do enunciado:**
- (a) "Cargas perigosas não podem ser devolvidas." → bate `nao podem` → **passa** corretamente.
- (b) "Não há impedimento para devolução de carga perigosa." → nenhum marcador bate literalmente (`nao ha devolucao` ≠ `nao ha impedimento para devolucao`) → **bloqueia** — correto, mas por sorte de não-match, não porque o código "entende" que a negação recai sobre "impedimento" e não sobre "devolução". O ponto que o enunciado quer ilustrar (negação que nega a coisa errada) é real; o exemplo acima com "não podemos... mas devolução... permitida" mostra o caso em que essa fragilidade realmente vaza.
- (c) "A devolução de material perigoso é permitida em casos excepcionais." → nenhum marcador bate → bloqueia corretamente.
- (d) "Cargas classificadas como perigosas (...) seguem regras à parte para devolução." → nenhum marcador bate → bloqueia. Frase é ambígua/neutra (não afirma nem nega); o comportamento *fail-closed* é aceitável para um guardrail de segurança, mas vale registrar como possível fonte de escalonamentos desnecessários.

**Correção proposta:** avaliar por sentença/cláusula, exigindo que a negação esteja na **mesma sentença** que menciona os dois tópicos:

```typescript
const SENTENCE_SPLIT_REGEX = /(?<=[.!?;\n])\s+|\n+/;

export const checkDangerousCargoReturnGuardrail = (answer: string): boolean => {
	const normalizedAnswer = normalizeText(answer);
	const sentences = normalizedAnswer
		.split(SENTENCE_SPLIT_REGEX)
		.filter((s) => s.trim().length > 0);

	const relevantSentences = sentences.filter(
		(sentence) => /perigos/.test(sentence) && /devolu/.test(sentence),
	);

	if (relevantSentences.length === 0) {
		return true;
	}

	return relevantSentences.every((sentence) =>
		NEGATION_MARKERS.some((marker) => sentence.includes(marker)),
	);
};
```

**Ressalva honesta:** isso resolve o caso em que os dois tópicos estão em sentenças diferentes, mas **não resolve 100%** cláusulas separadas por vírgula dentro da mesma sentença (ex.: o exemplo "não podemos... mas devolução... permitida" continua passando, porque a vírgula não quebra a sentença). Dividir por vírgula também traria risco de quebrar negações legítimas que atravessam vírgula (ex.: "carga perigosa, portanto, não pode ser devolvida"). Isso é uma limitação **inerente** a heurísticas de keyword/regex — o próprio código já reconhece isso no comentário original ("first-pass heuristic ... not full semantic understanding"). Recomendo, como item de follow-up, uma checagem semântica secundária (ex.: um segundo prompt estruturado tipo "esta resposta afirma ou nega a possibilidade de devolução de carga perigosa? responda apenas SIM/NÃO") para os casos em que o par de tópicos é detectado — usando o LLM como classificador binário de alta precisão em cima do sinal determinístico, em vez de tentar cobrir tudo em regex.

---

### P3 — Marcador `'excecao'` é ambíguo e pode indicar exatamente o oposto de negação

**Localização:** `NEGATION_MARKERS`

**O que está errado:** a palavra isolada `excecao` foi tratada como sinal de negação, mas "exceção" tipicamente introduz uma **permissão condicional**, não uma proibição.

**Por que é um problema real:** uma resposta como:
> "Há uma exceção que permite a devolução de cargas perigosas em casos de defeito de fabricação."

contém o substring `excecao` → `foundNegation = true` → o guardrail marca como **válido** uma resposta que está literalmente concedendo a devolução de carga perigosa. Isso é o tipo de falso negativo mais perigoso possível para este guardrail: o marcador criado para "proteger" está sendo usado para o conteúdo que deveria bloquear.

**Correção proposta:** remover o marcador ambíguo e, se necessário, usar apenas frases totalmente inequívocas:
```typescript
export const NEGATION_MARKERS = [
	'nao pode',
	'nao podem',
	'nao e elegivel',
	'nao sao elegiveis',
	'nao devem ser devolvidas',
	'nao deve ser devolvida',
	'nao aceita devolucao',
	'nao aceitamos devolucao',
	'nao ha devolucao',
	'nao e possivel devolver',
	'nao e permitida a devolucao',
	'nao e permitido devolver',
	'e proibida a devolucao',
	'e proibido devolver',
	'fica vedada a devolucao',
	'vedada a devolucao',
	'sem possibilidade de devolucao',
	'nao ha excecao para devolucao',
	'sem excecao para devolucao',
];
```
(também foram adicionados fraseados comuns que faltavam na lista original, como `"e proibida a devolucao"` e `"nao e permitida a devolucao"` — sem isso, respostas corretas com esse fraseado eram bloqueadas por falso positivo.)

---

### P4 — Detecção de tópico depende de radicais literais; sinônimos escapam do guardrail inteiramente

**Localização:** `hasDangerousTopic` / `hasReturnTopic`

**O que está errado:** os regexes `/perigos/` e `/devolu/` só disparam com esses radicais exatos. Qualquer resposta que descreva o mesmo cenário com outras palavras (`hazmat`, `material inflamável/radioativo/tóxico`, `retorno da mercadoria`, `reenvio do produto`) nunca entra no branch de verificação — `topicInPlay` fica `false` e a função retorna `true` (válido) sem checar negação nenhuma.

**Por que é um problema real:** é o caminho de escape (pergunta 4) mais amplo do módulo: o guardrail 2 simplesmente não existe para qualquer resposta que evite os dois radicais específicos, mesmo afirmando abertamente que a devolução é permitida.

**Por que não "corrigir" isso apenas adicionando sinônimos no regex:** expandir `hasReturnTopic` para incluir algo como `retorn` traria muitos falsos positivos (ex.: "retorno de contato", "prazo de retorno") sem validação de corpus real — trocaria um problema por outro sem dados que sustentem a mudança. Isso deveria ser um exercício orientado por auditoria de respostas reais do time de atendimento/jurídico, não uma lista adivinhada no code review.

**Correção proposta (mitigação segura, não definitiva):** documentar explicitamente o limite no próprio código (feito no arquivo corrigido) e abrir um item de follow-up para:
1. Auditar respostas reais para levantar sinônimos usados na prática;
2. Considerar a checagem semântica secundária mencionada em P2 como rede de segurança adicional para este guardrail especificamente, já que ele é o mais sensível dos dois.

---

## Resposta às 4 perguntas

1. **Campos extras são aceitos?** Sim, silenciosamente (modo `strip` padrão do Zod). Deveria ser `.strict()` — ver P1.
2. **A heurística cobre variações razoáveis?** Parcialmente. Ela acerta os 4 exemplos dados, mas isso mascarava um problema estrutural mais sério: a negação é buscada no texto inteiro, sem vínculo com a cláusula que faz a afirmação (P2), e um dos marcadores (`excecao`) pode inverter o resultado (P3). Também não cobre sinônimos fora dos radicais literais (P4).
3. **Guardrail 1 realmente bloqueia?** **Sim.** Quando `checkSourceDocumentGuardrail` retorna `false`, a função faz `return { valid: false, response: SAFE_FALLBACK_RESPONSE, ... }` antes de qualquer outra checagem — a resposta original nunca é repassada. Isso está correto e não precisa de correção.
4. **Existe caminho de escape não coberto?** Sim — o principal é P4 (sinônimos fora dos radicais `perigos`/`devolu`), seguido por P2/P3 (negação/marcador desconectados da cláusula real). O guardrail 1 não tem esse problema.

---

## O que está correto

- Arquitetura geral (schema → guardrail 1 → guardrail 2 → fallback) é sólida e legível.
- Guardrail 1 (`source_document` não vazio) está implementado corretamente, incluindo o cuidado de tratar string só-com-espaço via `.trim()`, e **realmente bloqueia e substitui** a resposta.
- `normalizeText` (lowercase + NFD + remoção de diacríticos) está tecnicamente correto para lidar com acentuação em PT-BR (verificado: "ção" → "cao", "não" → "nao" — consistente com a grafia usada em `NEGATION_MARKERS`).
- Decisão de **não** colocar `.min(1)` no schema para `source_document` e delegar isso ao guardrail 1 é uma separação de responsabilidades correta e bem documentada (schema = forma, guardrail = regra de negócio).
- Uso de `safeParse` (em vez de `parse` + try/catch) é a forma idiomática e correta no Zod para esse fluxo.
- Logs estruturados (`logger.warn`/`logger.info` com `event`) facilitam observabilidade e auditoria — bom para um harness de compliance.
- O comentário do código já é honesto sobre a natureza "first-pass heuristic" do guardrail 2 — isso facilitou identificar que os problemas eram esperados/conhecidos, não uma alegação falsa de robustez.

## Veredicto

**🚫 Bloqueador crítico**

O motivo é específico: o guardrail 2 — a única barreira determinística contra afirmar que devolução de carga perigosa é possível — tem um bypass demonstrável (P2/P3) usando fraseados plausíveis de um agente de atendimento real, não um ataque adversarial exótico. Como esse é literalmente o guardrail que justifica a existência do módulo, isso não deveria ir para produção sem as correções de P1–P3 no mínimo. P4 é um risco residual aceitável **desde que documentado e com follow-up aberto**, não um bloqueador por si só.

## Recomendação de follow-up (não bloqueante para este PR, mas deve virar ticket)

Validar `NEGATION_MARKERS` e os radicais de tópico com um corpus real de respostas do atendimento (ideal: casos históricos + red team interno), e avaliar adicionar a checagem semântica secundária mencionada em P2/P4 para o guardrail de carga perigosa, dado que ele lida com risco de segurança física, não só experiência do cliente.
