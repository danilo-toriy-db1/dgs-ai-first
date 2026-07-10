<!--
skill: typescript-conventions
level: foundation
applies-to: all TypeScript files in src/ and tests/
read-before: every Copilot prompt that generates .ts files
maintained-by: Tech Lead
-->

## Context

This skill defines the mandatory TypeScript coding conventions for NovaTech Assistant.
It exists to keep generated and hand-written code consistent with strict mode, Azure Functions v4, Zod validation, structured logging, and Vitest testing standards.
Follow these conventions in every file under src/ and tests/ to avoid rework in code review and runtime defects in production.

## Non-negotiable Rules

1. Never use `any`. Use `unknown` + type guards, or `z.infer<>` from Zod.
2. All environment variables must be read from src/shared/config.ts, never from process.env directly in business logic files.
3. All logging must use the pino logger from src/shared/logger.ts. Never use console.log, console.error, or console.warn.
4. Structured log events must include an `event` field as the first property (ex: { event: 'query_received', ...otherFields }).
5. Never log PII. The question content from users must never appear in logs - log questionLength (number) instead of the question text.
6. Azure Functions must use v4 API: app.http() registration at the bottom of the file, not module.exports at the top.
7. All async functions must handle errors with try/catch. Never let unhandled promise rejections propagate in Azure Functions.

## DO / DON'T Examples (one per rule)

### Rule 1 - Type safety without any

```typescript
// ✅ DO
import { z } from 'zod';

const FeedbackSchema = z.object({
	rating: z.number().int().min(1).max(5),
	comment: z.string().trim().min(1),
});

type FeedbackInput = z.infer<typeof FeedbackSchema>;

export function parseFeedback(payload: unknown): FeedbackInput {
	return FeedbackSchema.parse(payload);
}
```

```typescript
// ❌ DON'T
export function parseFeedback(payload: any): any {
	return payload;
}
```

### Rule 2 - Environment access only via shared config

```typescript
// ✅ DO
import { loadConfig } from '../../shared/config';

const config = loadConfig();

export function getSearchEndpoint(): string {
	return config.azureSearchEndpoint;
}
```

```typescript
// ❌ DON'T
export function getSearchEndpoint(): string {
	return process.env.AZURE_SEARCH_ENDPOINT ?? '';
}
```

### Rule 3 - Logging only through shared pino logger

```typescript
// ✅ DO
import { logger } from '../../shared/logger';

export function logHealthCheck(): void {
	logger.info({ event: 'health_check_ok', component: 'query-endpoint' });
}
```

```typescript
// ❌ DON'T
export function logHealthCheck(): void {
	console.log('health check ok');
}
```

### Rule 4 - Event-first structured logs

```typescript
// ✅ DO
import { logger } from '../../shared/logger';

export function logSearchFinished(resultCount: number, latencyMs: number): void {
	logger.info({
		event: 'search_finished',
		resultCount,
		latencyMs,
	});
}
```

```typescript
// ❌ DON'T
import { logger } from '../../shared/logger';

export function logSearchFinished(resultCount: number, latencyMs: number): void {
	logger.info({
		resultCount,
		latencyMs,
		event: 'search_finished',
	});
}
```

### Rule 5 - Never log user question content (PII)

```typescript
// ✅ DO
import { logger } from '../../shared/logger';

type QueryInput = {
	question: string;
	sessionId?: string;
};

export function logQueryReceived(input: QueryInput): void {
	logger.info({
		event: 'query_received',
		questionLength: input.question.length,
		sessionId: input.sessionId ?? null,
	});
}
```

```typescript
// ❌ DON'T
import { logger } from '../../shared/logger';

type QueryInput = {
	question: string;
};

export function logQueryReceived(input: QueryInput): void {
	logger.info({
		event: 'query_received',
		question: input.question,
	});
}
```

### Rule 6 - Azure Functions v4 registration style

```typescript
// ✅ DO
import {
	app,
	type HttpRequest,
	type HttpResponseInit,
	type InvocationContext,
} from '@azure/functions';

export async function queryHandler(
	request: HttpRequest,
	context: InvocationContext
): Promise<HttpResponseInit> {
	return {
		status: 200,
		jsonBody: { status: 'ok' },
	};
}

app.http('query', {
	methods: ['POST'],
	authLevel: 'function',
	route: 'query',
	handler: queryHandler,
});
```

```typescript
// ❌ DON'T
import type { AzureFunction } from '@azure/functions';

const httpTrigger: AzureFunction = async function (context, req) {
	context.res = {
		status: 200,
		body: { status: 'ok' },
	};
};

export default httpTrigger;
```

### Rule 7 - Mandatory try/catch in async Azure handlers

```typescript
// ✅ DO
import { type HttpRequest, type HttpResponseInit, type InvocationContext } from '@azure/functions';
import { logger } from '../../shared/logger';

export async function feedbackHandler(
	request: HttpRequest,
	context: InvocationContext
): Promise<HttpResponseInit> {
	try {
		const body: unknown = await request.json();

		logger.info({
			event: 'feedback_received',
			payloadType: typeof body,
		});

		return {
			status: 202,
			jsonBody: { status: 'accepted' },
		};
	} catch (error: unknown) {
		logger.error({
			event: 'feedback_handler_error',
			error: error instanceof Error ? error.message : 'Unknown error',
		});

		return {
			status: 500,
			jsonBody: { error: 'Internal server error' },
		};
	}
}
```

```typescript
// ❌ DON'T
import { type HttpRequest, type HttpResponseInit, type InvocationContext } from '@azure/functions';

export async function feedbackHandler(
	request: HttpRequest,
	context: InvocationContext
): Promise<HttpResponseInit> {
	const body = await request.json();
	await saveFeedback(body);

	return {
		status: 202,
		jsonBody: { status: 'accepted' },
	};
}

async function saveFeedback(value: unknown): Promise<void> {
	if (!value) {
		throw new Error('invalid value');
	}
}
```

## Anti-patterns to Avoid

- **Type Escape Hatch**: Copilot generates helper functions with `payload: any` and returns `any` to silence type errors quickly. This is rejected because it defeats strict mode and hides invalid shapes until runtime. Violates Rule 1.
- **Hidden Env Reads**: Copilot injects `process.env.X` directly into service modules like search, completion, or prompt builder. This is rejected because config becomes fragmented and hard to validate. Violates Rule 2.
- **Console Shortcut Logging**: Copilot emits `console.log` for debugging or `console.error` in catch blocks. This is rejected because logs are unstructured and cannot be reliably queried in observability pipelines. Violates Rule 3.
- **PII in Operational Logs**: Copilot logs complete user prompts for convenience while debugging retrieval quality. This is rejected due to privacy and compliance risk for customer input. Violates Rule 5.
- **Legacy Function Export Style**: Copilot generates default exports with older Azure Functions patterns (`context`, `req`, module-style handlers). This is rejected because NovaTech uses v4 app registration and explicit handler wiring. Violates Rule 6.

## Checklist (for self-review before opening a PR)

- [ ] No `any` appears in the file; if an exception exists, it has a clear inline justification comment.
- [ ] All input/output payloads are validated with Zod schemas and typed with `z.infer<>` where applicable.
- [ ] The file does not read `process.env` directly and uses configuration from `src/shared/config.ts`.
- [ ] Logging uses only the shared pino logger from `src/shared/logger.ts`.
- [ ] Every structured log object starts with `event` as the first property.
- [ ] No log line contains raw user question text or other PII; only metadata such as length or IDs is logged.
- [ ] Any Azure Function in the file uses v4 `app.http()` registration at the bottom.
- [ ] Every async entry point includes `try/catch` and maps failures to safe, controlled responses.
