import { app, type HttpRequest, type HttpResponseInit, type InvocationContext } from '@azure/functions';

import { logger } from '../../shared/logger';
import { QueryRequestSchema } from './validator';

/** Handles incoming query requests and validates the payload before acceptance. */
async function queryHandler(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  try {
    const body: unknown = await request.json();
    const validation = QueryRequestSchema.safeParse(body);

    if (!validation.success) {
      logger.warn({
        event: 'query_validation_failed',
        errorCount: validation.error.issues.length,
      });

      return {
        status: 400,
        jsonBody: {
          error: 'Invalid request',
          details: validation.error.flatten(),
        },
      };
    }

    const validatedData = validation.data;

    logger.info({
      event: 'query_received',
      questionLength: validatedData.question.length,
      sessionId: validatedData.sessionId ?? null,
    });

    return {
      status: 200,
      jsonBody: {
        status: 'accepted',
        message: 'Query received — processing not yet implemented',
        sessionId: validatedData.sessionId ?? null,
      },
    };
  } catch (error: unknown) {
    logger.error({
      event: 'query_handler_error',
      error: error instanceof Error ? error.message : 'Unknown error',
    });

    return {
      status: 500,
      jsonBody: {
        error: 'Internal server error',
      },
    };
  }
}

export { queryHandler };

app.http('query', {
  methods: ['POST'],
  authLevel: 'function',
  route: 'api/query',
  handler: queryHandler,
});
