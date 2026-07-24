import { HttpRequest, HttpResponseInit, app } from "@azure/functions";
import { z } from "zod";

import { getCosmosClient } from "../../shared/config";
import { logger } from "../../shared/logger";

const FEEDBACK_DATABASE_ID = "novatech";
const FEEDBACK_CONTAINER_ID = "feedbacks";
const MAX_COMMENT_LENGTH = 2000;

export const FeedbackRequestSchema = z.object({
  queryId: z.string().min(1),
  rating: z.number().int().min(1).max(5),
  comment: z.string().max(MAX_COMMENT_LENGTH).optional(),
  attendantEmail: z.string().email(),
});

type FeedbackRequest = z.infer<typeof FeedbackRequestSchema>;

type FeedbackDocument = FeedbackRequest & {
  timestamp: string;
};

type CosmosLikeError = {
  code?: number | string;
  statusCode?: number;
  message?: string;
};

let cachedContainer:
  | ReturnType<ReturnType<typeof getCosmosClient>["database"]>["container"]
  | undefined;

function getFeedbackContainer() {
  if (!cachedContainer) {
    const cosmosClient = getCosmosClient();
    cachedContainer = cosmosClient
      .database(FEEDBACK_DATABASE_ID)
      .container(FEEDBACK_CONTAINER_ID);
  }

  return cachedContainer;
}

function isCosmosError(error: unknown): error is CosmosLikeError {
  if (!error || typeof error !== "object") {
    return false;
  }

  const candidate = error as CosmosLikeError;
  const hasStatusCode = typeof candidate.statusCode === "number";
  const hasNumericCode = typeof candidate.code === "number";
  const hasKnownCode =
    typeof candidate.code === "string" &&
    ["ECONNREFUSED", "ETIMEDOUT", "ENOTFOUND", "TimeoutError"].includes(
      candidate.code,
    );

  return hasStatusCode || hasNumericCode || hasKnownCode;
}

/**
 * Recebe feedback de respostas do assistente, valida o payload e persiste o
 * documento no Cosmos DB sem expor dados pessoais nos logs de observabilidade.
 */
export async function feedbackHandler(
  request: HttpRequest,
): Promise<HttpResponseInit> {
  let queryIdForLogging: string | undefined;
  
  try {
    let rawBody: unknown;

    try {
      rawBody = await request.json();
    } catch {
      return {
        status: 400,
        jsonBody: {
          error: "invalid_request_body",
          details: "Request body must be valid JSON.",
        },
      };
    }

    const parsedBody = FeedbackRequestSchema.safeParse(rawBody);

    if (!parsedBody.success) {
      return {
        status: 400,
        jsonBody: {
          error: "validation_failed",
          details: parsedBody.error.flatten(),
        },
      };
    }

    const validatedFeedback: FeedbackRequest = parsedBody.data;
    queryIdForLogging = validatedFeedback.queryId;

    const feedback: FeedbackDocument = {
      ...validatedFeedback,
      timestamp: new Date().toISOString(),
    };

    logger.info({
      event: "feedback_received",
      queryId: feedback.queryId,
      rating: feedback.rating,
      commentLength: feedback.comment?.length ?? 0,
    });

    const container = getFeedbackContainer();
    await container.items.create(feedback);

    return {
      status: 200,
      jsonBody: {
        status: "accepted",
        queryId: feedback.queryId,
      },
    };
  } catch (error: unknown) {
    if (isCosmosError(error)) {
      logger.error({
        event: "feedback_storage_failed",
        queryId: queryIdForLogging ?? "unknown",
        reason: "cosmos_unavailable",
      });

      return {
        status: 502,
        jsonBody: {
          error: "storage_unavailable",
        },
      };
    }

    logger.error({
      event: "feedback_handler_unexpected_error",
      reason: "unexpected_error",
    });

    return {
      status: 500,
      jsonBody: {
        error: "internal_server_error",
      },
    };
  }
}

app.http("feedback", {
  methods: ["POST"],
  authLevel: "function",
  handler: feedbackHandler,
});