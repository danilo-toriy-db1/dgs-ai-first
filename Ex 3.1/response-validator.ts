import { z } from 'zod';

import { logger } from '../shared/logger';

/**
 * Deterministic harness for LLM output validation after generation.
 * The system prompt asks the model to cite sources and deny dangerous cargo returns,
 * but prompt instructions are probabilistic and not guarantees.
 * This module enforces those rules in code before any answer reaches the atendente.
 * Invalid outputs are rejected programmatically and replaced with a safe fallback.
 */
export const StructuredAssistantResponseSchema = z
	.object({
		answer: z.string(),
		/**
		 * No .min(1) here by design: schema validates shape/type only.
		 * Business enforcement for non-empty source_document is handled by Guardrail 1.
		 */
		source_document: z.string(),
		confidence_score: z.number().min(0).max(1),
	})
	// .strict(): campos inesperados no payload indicam drift de contrato entre
	// o gerador (LLM/pipeline RAG) e este harness. Preferimos falhar de forma
	// auditável (fallback + log) a descartar silenciosamente dados que podem
	// sinalizar um problema de integração upstream (ex.: campo renomeado,
	// versão de payload divergente).
	.strict();

export type StructuredAssistantResponse = z.infer<typeof StructuredAssistantResponseSchema>;

export const SAFE_FALLBACK_RESPONSE: StructuredAssistantResponse = {
	answer:
		'Não foi possível confirmar esta resposta automaticamente. Recomendamos escalar para o supervisor de atendimento antes de repassar qualquer informação ao cliente.',
	source_document: 'N/A — validação de harness falhou',
	confidence_score: 0,
};

/**
 * Frases que representam uma NEGAÇÃO EXPLÍCITA da possibilidade de devolução.
 * Já normalizadas: minúsculas e sem diacríticos (ver normalizeText).
 *
 * IMPORTANTE: nenhum marcador aqui deve ser uma palavra "neutra" que também
 * apareça em frases que CONCEDEM devolução por exceção (ex.: a antiga entrada
 * isolada "excecao" foi removida por esse motivo — ela também aparece em
 * frases como "há uma exceção que permite a devolução...").
 */
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

export const checkSourceDocumentGuardrail = (response: StructuredAssistantResponse): boolean =>
	response.source_document.trim().length > 0;

const normalizeText = (text: string): string =>
	text
		.toLowerCase()
		.normalize('NFD')
		.replace(/[\u0300-\u036f]/g, '');

// Split grosseiro em sentenças/cláusulas (por pontuação forte). Não é um
// parser de PT-BR completo — cláusulas separadas apenas por vírgula na mesma
// sentença ainda podem "vazar" negação de um assunto para outro. Isso é uma
// limitação conhecida de heurísticas por regex; ver nota abaixo.
const SENTENCE_SPLIT_REGEX = /(?<=[.!?;\n])\s+|\n+/;

/**
 * First-pass heuristic using keyword co-occurrence and negation markers,
 * not full semantic understanding.
 *
 * A checagem é feita POR SENTENÇA: só exigimos negação explícita nas
 * sentenças que efetivamente mencionam carga perigosa E devolução juntas,
 * em vez de buscar negação no texto inteiro. Isso evita que (a) uma negação
 * sobre um assunto não relacionado "salve" uma afirmação de permissão em
 * outra frase, e que (b) tópicos mencionados em frases diferentes e não
 * relacionadas disparem um bloqueio desnecessário.
 *
 * LIMITAÇÕES CONHECIDAS (revisar/iterar conforme corpus real):
 * 1. Cláusulas separadas apenas por vírgula dentro da MESMA sentença ainda
 *    podem contaminar o resultado (ex.: "não podemos garantir o prazo, mas a
 *    devolução de carga perigosa é permitida"). Resolver isso de forma
 *    confiável exige análise gramatical real, não regex.
 * 2. A detecção de tópico depende dos radicais literais "perigos" e
 *    "devolu". Respostas que usam sinônimos (ex. "hazmat", "retorno da
 *    mercadoria") não acionam este guardrail.
 * Para os dois pontos acima, recomenda-se uma checagem semântica secundária
 * (ex.: um segundo prompt estruturado perguntando explicitamente "esta
 * resposta afirma ou nega a devolução de carga perigosa?") como rede de
 * segurança adicional, em vez de tentar cobrir 100% dos casos em regex.
 */
export const checkDangerousCargoReturnGuardrail = (answer: string): boolean => {
	const normalizedAnswer = normalizeText(answer);
	const sentences = normalizedAnswer
		.split(SENTENCE_SPLIT_REGEX)
		.filter((sentence) => sentence.trim().length > 0);

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

export type ValidationResult =
	| { valid: true; response: StructuredAssistantResponse }
	| { valid: false; response: StructuredAssistantResponse; rejectionReason: string };

export const validateAssistantResponse = (rawOutput: unknown): ValidationResult => {
	const parseResult = StructuredAssistantResponseSchema.safeParse(rawOutput);

	if (!parseResult.success) {
		logger.warn({
			event: 'response_schema_validation_failed',
			issueCount: parseResult.error.issues.length,
		});

		return {
			valid: false,
			response: SAFE_FALLBACK_RESPONSE,
			rejectionReason: 'schema_validation_failed',
		};
	}

	if (!checkSourceDocumentGuardrail(parseResult.data)) {
		logger.warn({
			event: 'guardrail_failed',
			guardrail: 'source_document_required',
		});

		return {
			valid: false,
			response: SAFE_FALLBACK_RESPONSE,
			rejectionReason: 'missing_source_document',
		};
	}

	if (!checkDangerousCargoReturnGuardrail(parseResult.data.answer)) {
		logger.warn({
			event: 'guardrail_failed',
			guardrail: 'dangerous_cargo_return_negation',
		});

		return {
			valid: false,
			response: SAFE_FALLBACK_RESPONSE,
			rejectionReason: 'dangerous_cargo_return_not_negated',
		};
	}

	logger.info({
		event: 'response_validated',
		confidenceScore: parseResult.data.confidence_score,
	});

	return {
		valid: true,
		response: parseResult.data,
	};
};
