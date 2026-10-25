import type {
  LLMClient,
  LLMTurnInput,
  LLMResponse,
  LLMUsage,
} from "@openreel/agent";
import { makeNodeLLMClient } from "./node-llm";
import {
  ServerManager,
  type ServerManagerSpec,
  type SpawnFn,
  type SpawnResult,
} from "./server-manager";
import {
  evaluateCostGate,
  CostGateError,
  type CostGateDecision,
  type CostGateEvidence,
} from "./cost-gate";

/** Provider names. anthropic/openai are HTTP (BYOK); codex/pi are command. */
export type ProviderName = "anthropic" | "openai" | "codex" | "pi";

/**
 * A provider descriptor. It describes the call-form (transport, default model,
 * gateway, and — for command providers — the ServerManager spec factory).
 * Registration here is NOT a live call: the cost gate (cost-gate.ts) decides
 * whether a built client may actually fire.
 */
export interface ProviderDescriptor {
  readonly name: ProviderName;
  readonly transport: "http" | "command";
  /** HTTP: the makeNodeLLMClient provider name. */
  readonly llmProvider?: "anthropic" | "openai";
  /** Default model (command: from the local/LAN gateway config). */
  readonly model: string;
  /** The gateway the provider targets (documented; not a live default). */
  readonly gateway: string;
  /** Command: the provider name the underlying CLI expects (pi --provider). */
  readonly cliProvider?: string;
  /** Command: builds the ServerManager spec for a given model. */
  readonly commandSpec?: (model: string) => ServerManagerSpec;
  /** Upstream billing verification; absent = unverified (rejects live call). */
  readonly upstreamVerification?: CostGateEvidence;
}

/**
 * Registry. codex and pi are registered (call-form only); their upstream
 * billing is UNVERIFIED, so buildClient() rejects a live call for them. The
 * descriptors document the actual local/LAN gateways (read from the member's
 * configs), NOT a claim that a live call is connected or zero-pay.
 */
export const PROVIDER_DESCRIPTORS: Record<ProviderName, ProviderDescriptor> = {
  anthropic: {
    name: "anthropic",
    transport: "http",
    llmProvider: "anthropic",
    model: "claude-sonnet-5",
    gateway: "https://api.anthropic.com/v1/messages",
  },
  openai: {
    name: "openai",
    transport: "http",
    llmProvider: "openai",
    model: "gpt-5.6-sol",
    gateway: "https://api.openai.com/v1/chat/completions",
  },
  // codex CLI → local sub2api (127.0.0.1:15721) → qwen3.8-27b-office.
  // The key would come from the member's formal settings UI; upstream billing
  // is unverified, so buildClient() rejects a live call (registers only).
  codex: {
    name: "codex",
    transport: "command",
    model: "qwen3.8-27b-office",
    gateway: "http://127.0.0.1:15721/v1",
    commandSpec: (model) => ({
      command: "codex",
      buildArgs: () => ["exec", "--json", "-m", model],
      stdin: (input) => renderPrompt(input),
      parseOutput: parseCodexOutput,
    }),
  },
  // pi CLI → LAN gateway (192.168.31.154:10013) → qwen3.8-27b-office.
  // OpenAI-compatible; upstream billing is unverified, so buildClient() rejects
  // a live call (待验证 / 未覆盖; not connected, not claimed as zero-pay).
  pi: {
    name: "pi",
    transport: "command",
    model: "qwen3.8-27b-office",
    gateway: "http://192.168.31.154:10013",
    cliProvider: "hh",
    commandSpec: (model) => ({
      command: "pi",
      buildArgs: (input) => [
        "--print",
        "--mode",
        "json",
        "--provider",
        "hh",
        "--model",
        model,
        renderPrompt(input),
      ],
      parseOutput: parsePiOutput,
    }),
  },
};

export function listProviders(): ProviderName[] {
  return Object.keys(PROVIDER_DESCRIPTORS) as ProviderName[];
}

export interface BuildClientOptions {
  readonly provider: ProviderName;
  /** Model override (defaults to the descriptor's model). */
  readonly model?: string;
  /** Non-empty key from the member's formal settings (never echoed/stored). */
  readonly hasApiKey?: boolean;
  /** HTTP BYOK key (never stored/logged); only read for the Authorization header. */
  readonly apiKey?: string;
  /** Upstream billing verification (a future task may supply this). */
  readonly upstreamVerification?: CostGateEvidence;
  /** Injected spawner for command providers (tests); production uses child_process. */
  readonly spawn?: SpawnFn;
  /** HTTP transport override (tests). */
  readonly fetchFn?: typeof fetch;
  readonly maxTokens?: number;
}

/**
 * Build an LLMClient for a provider, applying the cost gate.
 *  - HTTP (anthropic/openai): needs a BYOK key; no key → CostGateError on call.
 *  - Command (codex/pi): the call-form is built; a live call only fires if the
 *    cost gate allows it (upstream verified). Unverified → the returned client
 *    rejects on complete() WITHOUT spawning (待验证 / 未覆盖).
 *
 * The gate never configures or echoes a key. A provider may be registered
 * (described) without being callable (a live call may be permitted).
 */
export function buildClient(opts: BuildClientOptions): LLMClient {
  const descriptor = PROVIDER_DESCRIPTORS[opts.provider];
  if (!descriptor) {
    throw new CostGateError({
      allowed: false,
      reason: "unknown-provider",
      message: `${opts.provider}: unknown provider.`,
    });
  }
  const hasApiKey =
    opts.hasApiKey ?? (opts.apiKey ? opts.apiKey.length > 0 : false);
  const decision = evaluateCostGate({
    provider: opts.provider,
    transport: descriptor.transport,
    hasApiKey,
    upstreamVerification:
      opts.upstreamVerification ?? descriptor.upstreamVerification,
  });
  const model = opts.model ?? descriptor.model;

  if (descriptor.transport === "http") {
    if (!decision.allowed) throw new CostGateError(decision);
    return makeNodeLLMClient({
      provider: descriptor.llmProvider!,
      model,
      apiKey: opts.apiKey ?? "",
      maxTokens: opts.maxTokens,
      fetchFn: opts.fetchFn,
    });
  }
  // command: build the call-form, then gate a live call behind the decision.
  const spec = descriptor.commandSpec!(model);
  const inner = new ServerManager({ ...spec, spawn: opts.spawn });
  return new GatedClient(inner, decision);
}

/**
 * Wraps an inner client so a live call only fires when the cost gate allowed
 * it. If the gate rejected (e.g. unverified upstream / no key), complete()
 * throws a CostGateError and the inner command is NEVER spawned.
 */
class GatedClient implements LLMClient {
  constructor(
    private readonly inner: LLMClient,
    private readonly decision: CostGateDecision,
  ) {}
  async complete(input: LLMTurnInput): Promise<LLMResponse> {
    if (!this.decision.allowed) {
      throw new CostGateError(this.decision);
    }
    return this.inner.complete(input);
  }
}

// ---- Prompt rendering -------------------------------------------------------

/** Render a turn into a single prompt string for a command coding agent. */
export function renderPrompt(input: LLMTurnInput): string {
  const parts: string[] = [];
  if (input.system) parts.push(input.system);
  for (const m of input.messages) {
    if (m.role === "user") {
      parts.push(`User: ${m.content}`);
    } else if (m.role === "assistant") {
      const body =
        m.content ||
        (m.toolUses.length ? `[${m.toolUses.length} tool call(s)]` : "");
      parts.push(`Assistant: ${body}`);
    } else {
      const lines = m.results.map((r) => {
        const content = typeof r.content === "string" ? r.content : "[blocks]";
        return `  - ${r.toolUseId}: ${content}`;
      });
      parts.push(`Tool results:\n${lines.join("\n")}`);
    }
  }
  return parts.join("\n\n");
}

// ---- Output parsing ---------------------------------------------------------

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Walk OpenAI-compatible / nested content shapes to plain text. */
function extractTextFromUnknown(v: unknown): string {
  if (typeof v === "string") return v;
  if (Array.isArray(v)) {
    return v
      .map((x) => extractTextFromUnknown(x))
      .filter(Boolean)
      .join("");
  }
  if (isRecord(v)) {
    if (typeof v.text === "string") return v.text;
    const c = v.content;
    if (typeof c === "string") return c;
    if (Array.isArray(c)) {
      return c
        .map((x) => extractTextFromUnknown(x))
        .filter(Boolean)
        .join("");
    }
  }
  return "";
}

function extractMessageText(event: unknown): string {
  if (!isRecord(event)) return "";
  if (typeof event.text === "string") return event.text;
  if (typeof event.content === "string") return event.content;
  const msg = event.message;
  if (isRecord(msg)) {
    if (typeof msg.content === "string") return msg.content;
    if (Array.isArray(msg.content)) {
      return msg.content
        .map((x) => extractTextFromUnknown(x))
        .filter(Boolean)
        .join("");
    }
  }
  if (Array.isArray(event.choices)) {
    for (const choice of event.choices) {
      if (isRecord(choice) && isRecord(choice.message)) {
        const t = extractTextFromUnknown(choice.message.content);
        if (t) return t;
      }
    }
  }
  if (Array.isArray(event.content)) {
    return event.content
      .map((x) => extractTextFromUnknown(x))
      .filter(Boolean)
      .join("");
  }
  return "";
}

function extractUsage(event: unknown): LLMUsage | undefined {
  if (!isRecord(event)) return undefined;
  const u = event.usage;
  if (!isRecord(u)) return undefined;
  const inTok =
    typeof u.input_tokens === "number"
      ? u.input_tokens
      : typeof u.prompt_tokens === "number"
        ? u.prompt_tokens
        : undefined;
  const outTok =
    typeof u.output_tokens === "number"
      ? u.output_tokens
      : typeof u.completion_tokens === "number"
        ? u.completion_tokens
        : undefined;
  if (inTok === undefined && outTok === undefined) return undefined;
  return { inputTokens: inTok ?? 0, outputTokens: outTok ?? 0 };
}

/**
 * Parse `codex exec --json` output (JSONL events) into an LLMResponse. The
 * final (last) text-bearing event is the response; usage is taken if present.
 * Exercised via canned output — the live output format is not verified
 * (待验证 / 未覆盖), so a non-zero exit is treated as a failure, not a blank.
 */
function parseCodexOutput(result: SpawnResult): LLMResponse {
  const { stdout, code } = result;
  if (code !== 0) {
    const detail =
      result.stderr.trim().slice(0, 500) || stdout.trim().slice(0, 500);
    throw new Error(`codex exited with code ${code}: ${detail}`);
  }
  const lines = stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  let text = "";
  let usage: LLMUsage | undefined;
  for (const line of lines) {
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      continue; // skip non-JSON lines
    }
    const t = extractMessageText(event);
    if (t) text = t; // last text-bearing event wins
    const u = extractUsage(event);
    if (u) usage = u;
  }
  return {
    text: text.trim(),
    toolUses: [],
    stopReason: "end_turn",
    usage,
  };
}

/**
 * Parse `pi --print --mode json` output (a JSON object; OpenAI-compatible or
 * simple {text|message|content}) into an LLMResponse. Exercised via canned
 * output — the live output format is not verified (待验证 / 未覆盖).
 */
function parsePiOutput(result: SpawnResult): LLMResponse {
  const { stdout, code } = result;
  if (code !== 0) {
    const detail =
      result.stderr.trim().slice(0, 500) || stdout.trim().slice(0, 500);
    throw new Error(`pi exited with code ${code}: ${detail}`);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout.trim());
  } catch {
    const match = stdout.match(/\{[\s\S]*\}/);
    if (!match) {
      throw new Error(`pi produced no parseable JSON: ${stdout.slice(0, 200)}`);
    }
    try {
      parsed = JSON.parse(match[0]);
    } catch {
      throw new Error(`pi produced invalid JSON: ${stdout.slice(0, 200)}`);
    }
  }
  return {
    text: extractMessageText(parsed).trim(),
    toolUses: [],
    stopReason: "end_turn",
    usage: extractUsage(parsed),
  };
}
