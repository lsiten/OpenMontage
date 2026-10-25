import {
  withRetry,
  makeClientFromSend,
  llmHttpError,
  parseRetryAfterMs,
} from "@openreel/agent";
import type { LLMClient, LLMSend, LlmProviderName } from "@openreel/agent";
import { COMMAND_PROVIDERS, makeCommandLLMClient } from "./command-llm";

/** HTTP providers (BYOK fetch) + command providers (server-manager pattern). */
export type LlmProvider = "anthropic" | "openai" | "codex" | "pi";

const ENDPOINTS: Record<"anthropic" | "openai", string> = {
  anthropic: "https://api.anthropic.com/v1/messages",
  openai: "https://api.openai.com/v1/chat/completions",
};

function authHeaders(
  provider: "anthropic" | "openai",
  apiKey: string,
): Record<string, string> {
  if (provider === "anthropic") {
    return {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    };
  }
  return {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  };
}

/**
 * Builds a fetch-based transport for the agent LLM clients. The API key is used
 * per-request for the Authorization header only and is never stored or logged —
 * preserving the BYOK no-persist guarantee on the server side.
 *
 * Command providers (codex/pi) are NOT HTTP transports: use makeNodeLLMClient,
 * which routes them to the command layer. Calling this with a command provider
 * is an explicit error (no placeholder / no silent fallback).
 */
export function makeNodeLLMSend(
  provider: LlmProvider,
  apiKey: string,
  fetchFn: typeof fetch = fetch,
): LLMSend {
  if (provider === "codex" || provider === "pi") {
    throw new Error(
      `Provider '${provider}' is a command provider; use makeNodeLLMClient ` +
        "(which routes it to the command layer), not an HTTP send.",
    );
  }
  const httpProvider: "anthropic" | "openai" = provider;
  if (!apiKey) {
    throw new Error(`Missing API key for provider '${provider}'`);
  }
  return async (body: unknown): Promise<unknown> => {
    const res = await fetchFn(ENDPOINTS[httpProvider], {
      method: "POST",
      headers: authHeaders(httpProvider, apiKey),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw llmHttpError(
        provider,
        res.status,
        text,
        parseRetryAfterMs(res.headers.get("retry-after")),
      );
    }
    return res.json();
  };
}

export interface NodeLLMOptions {
  readonly provider: LlmProvider;
  readonly model: string;
  readonly apiKey: string;
  readonly maxTokens?: number;
  readonly fetchFn?: typeof fetch;
}

export function makeNodeLLMClient(opts: NodeLLMOptions): LLMClient {
  // Command providers (codex/pi) use the server-manager pattern with a cost
  // gate; they never touch the HTTP transport or an API key here.
  if (opts.provider === "codex" || opts.provider === "pi") {
    return makeCommandLLMClient({ spec: COMMAND_PROVIDERS[opts.provider] });
  }
  const send = withRetry(makeNodeLLMSend(opts.provider, opts.apiKey, opts.fetchFn));
  return makeClientFromSend({
    provider: opts.provider as LlmProviderName,
    model: opts.model,
    maxTokens: opts.maxTokens,
    send,
  });
}
