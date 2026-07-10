import { z } from 'zod';

/** Schema for validating incoming query requests before the endpoint processes them. */
export const QueryRequestSchema = z.object({
	question: z.string().trim().min(1).max(2000),
	userId: z.string().optional(),
	sessionId: z.string().uuid().optional(),
});

export type QueryRequest = z.infer<typeof QueryRequestSchema>;

/** Schema for validating query endpoint responses returned to callers. */
export const QueryResponseSchema = z.object({
	answer: z.string(),
	source_document: z.string(),
	source_section: z.string(),
	confidence_score: z.number().min(0).max(1),
	session_id: z.string().optional(),
});

export type QueryResponse = z.infer<typeof QueryResponseSchema>;
