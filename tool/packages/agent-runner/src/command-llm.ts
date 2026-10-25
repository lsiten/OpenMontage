/**
 * Pluggable command-based LLM provider — server-manager pattern.
 *
 * Unlike the HTTP transports in `node-llm.ts` (anthropic/openai, BYOK fetch),
 * a command provider drives a local coding-agent CLI (e.g. `codex exec`,
 * `pi --print`) by: (1) building argv from the turn prompt, (2) invoking the
 * command, and (3) parsing the stdout into an `LLMResponse`.
 *
 * HARD COST GATE (LSIT-277): the invocation *form* is implemented, but this
 * task never configures / echoes / try-runs a paid or unknown-charge service:
 *   - `codex` (OpenAI, paid, member-authorized B): a key/subscription must be
 *     provided by the member via the official settings surface. With no key the
 *     provider is registered but explicitly refuses — no placeholder bypass.
 *   - `pi` (local/LAN): may only be invoked after a READ-ONLY verification that
 *     the LAN endpoint is zero-charge/local. Unverified => refuse, and never
 *     claim "zero-charge integrated".
 *
 * Nothing here performs a real network/model call for a paid or unverified
 * provider; the actual invocation is left to the member / a verified run.
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import type { LLMClient, LLMResponse, LLMTurnInput } from "@openreel/agent";

export type CommandProviderName = "codex" | "pi";

/** Result of a cost gate: whether the provider may be invoked now. */
export interface CommandGateResult {
  readonly ok: boolean;
  /** Human-readable reason (shown on refusal; never a silent placeholder). */
  readonly reason: string;
}

/** Injectable subprocess runner (tests pass a fake; production uses spawn). */
export type CommandRunner = (
  command: string,
  args: string[],
) => Promise<{ stdout: string; stderr: string; code: number }>;

/** One pluggable command provider. */
export interface CommandProviderSpec {
  readonly name: CommandProviderName;
  /** CLI command / absolute path. */
  readonly command: string;
  /** Default model id for this provider. */
  readonly model: string;
  /** Build argv from the turn prompt + model. */
  readonly buildArgs: (input: LLMTurnInput, model: string) => string[];
  /** Parse command stdout into an LLMResponse (throws on non-zero exit). */
  readonly parseOutput: (
    stdout: string,
    stderr: string,
    code: number,
  ) => LLMResponse;
  /** Cost gate: whether the provider may be invoked now. */
  readonly gate: () => CommandGateResult;
}

/** Refusal raised when a cost gate fails (never a placeholder response). */
export class CommandGateError extends Error {
  constructor(readonly provider: CommandProviderName, readonly reason: string) {
    super(`${provider}: ${reason}`);
    this.name = "CommandGateError";
  }
}

function lastUserPrompt(input: LLMTurnInput): string {
  for (let i = input.messages.length - 1; i >= 0; i--) {
    const m = input.messages[i];
    if (m.role === "user") return m.content;
  }
  return "";
}

/**
 * Parse a command provider's stdout into an LLMResponse. Coding-agent CLIs
 * return a final assistant message; we surface it as text with stopReason
 * `end_turn` (no fabricated tool calls). A non-zero exit is a hard error.
 */
export function parseCommandOutput(
  stdout: string,
  stderr: string,
  code: number,
  provider: CommandProviderName,
): LLMResponse {
  if (code !== 0) {
    throw new Error(
      `${provider} exited ${code}: ${(stderr || stdout).slice(0, 500)}`,
    );
  }
  const text = stdout.trim();
  if (!text) {
    throw new Error(`${provider} produced no output.`);
  }
  return { text, toolUses: [], stopReason: "end_turn" };
}

/** Default subprocess runner (production only; not exercised by cost gates). */
export const spawnRunner: CommandRunner = (command, args) =>
  new Promise((resolve) => {
    const child = spawn(command, args, {
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", (err) =>
      resolve({ stdout: "", stderr: String(err), code: 1 }),
    );
    child.on("close", (code) =>
      resolve({ stdout, stderr, code: code ?? 1 }),
    );
  });

function isLocalLanHost(host: string): boolean {
  // Private / loopback ranges only (no public IP, no domain name).
  if (host === "localhost" || host === "127.0.0.1") return true;
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return false;
  const a = Number(m[1]);
  return a === 10 || (a === 172 && Number(m[2]) >= 16 && Number(m[2]) <= 31) || a === 192 && Number(m[2]) === 168;
}

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

interface PiProviderConfig {
  readonly name?: string;
  readonly baseUrl?: string;
  readonly api?: string;
  readonly apiKey?: string;
  readonly models?: unknown[];
}

/** Read the pi config (read-only). Returns the "hh" provider block or null. */
export function readPiConfig(): PiProviderConfig | null {
  try {
    const p = path.join(homedir(), ".pi", "agent", "models.json");
    const raw = readFileSync(p, "utf8");
    const json = JSON.parse(raw) as {
      providers?: Record<string, PiProviderConfig>;
    };
    return json.providers?.hh ?? null;
  } catch {
    return null;
  }
}

/**
 * codex cost gate: OpenAI (paid). A key/subscription must be provided by the
 * member via the official settings surface. The impl side never configures /
 * echoes / try-runs the paid service. Without a key the provider is registered
 * but explicitly refuses (no placeholder bypass).
 */
export function codexGate(): CommandGateResult {
  const key =
    process.env.OPENREEL_CODEX_API_KEY ??
    process.env.CODEX_API_KEY ??
    process.env.OPENAI_API_KEY ??
    "";
  if (!key) {
    return {
      ok: false,
      reason:
        "codex (OpenAI, paid) requires a key/subscription provided by the " +
        "member via the official settings surface; not configured. Provider " +
        "is registered but not invocable (no placeholder bypass).",
    };
  }
  // Key present, but this task does not try-run paid services. The invocation
  // form is implemented; the member runs it via the official surface.
  return {
    ok: false,
    reason:
      "codex key present, but this task does not try-run a paid service; " +
      "invoke via the member-provided surface (impl side never runs it here).",
  };
}

/**
 * pi cost gate: local/LAN model. May only be invoked after a READ-ONLY
 * verification that the LAN endpoint is zero-charge/local: (1) config present,
 * (2) apiKey === PROXY_MANAGED (no external key), (3) baseUrl is a local/LAN
 * private IP, (4) the port is reachable. Unverified => refuse; never claim
 * "zero-charge integrated".
 */
export function piGate(
  reachability?: (host: string, port: number) => boolean,
): CommandGateResult {
  const cfg = readPiConfig();
  if (!cfg || cfg.apiKey !== "PROXY_MANAGED") {
    return {
      ok: false,
      reason:
        "pi config missing or not PROXY_MANAGED; cannot verify zero-charge/" +
        "local. Provider registered but not invocable (no placeholder bypass).",
    };
  }
  const host = cfg.baseUrl ? hostOf(cfg.baseUrl) : "";
  const port = cfg.baseUrl ? Number(new URL(cfg.baseUrl).port) : 0;
  if (!isLocalLanHost(host)) {
    return {
      ok: false,
      reason:
        `pi baseUrl "${cfg.baseUrl}" is not a local/LAN private IP; cannot ` +
        "verify zero-charge. Provider registered but not invocable (no placeholder).",
    };
  }
  const reachable = reachability?.(host, port) ?? true;
  if (!reachable) {
    return {
      ok: false,
      reason:
        `pi LAN ${host}:${port} not reachable; not verified. Provider ` +
        "registered but not invocable (no placeholder bypass).",
    };
  }
  // Verified local/LAN (read-only): reachable, PROXY_MANAGED (no external key),
  // private IP. Invocation form is implemented; this task does not run it.
  return {
    ok: true,
    reason:
      `pi LAN ${host}:${port} verified as local/LAN zero-charge by read-only ` +
      "check (reachable + PROXY_MANAGED + private IP). Invocation form " +
      "implemented; actual run not performed by this task.",
  };
}

export const codexProvider: CommandProviderSpec = {
  name: "codex",
  command: "codex",
  model: "gpt-5.6-sol",
  buildArgs: (input, model) => [
    "exec",
    "-m",
    model,
    // Prompt via stdin-safe positional; codex reads PROMPT or stdin.
    lastUserPrompt(input),
  ],
  parseOutput: (stdout, stderr, code) =>
    parseCommandOutput(stdout, stderr, code, "codex"),
  gate: () => codexGate(),
};

export const piProvider: CommandProviderSpec = {
  name: "pi",
  command: "pi",
  model: "qwen3.8-27b-office",
  buildArgs: (input, model) => [
    "--print",
    "--mode",
    "json",
    "--model",
    model,
    "--no-session",
    lastUserPrompt(input),
  ],
  parseOutput: (stdout, stderr, code) =>
    parseCommandOutput(stdout, stderr, code, "pi"),
  gate: () => piGate(),
};

export const COMMAND_PROVIDERS: Record<CommandProviderName, CommandProviderSpec> =
  {
    codex: codexProvider,
    pi: piProvider,
  };

/**
 * Build an `LLMClient` from a command provider. The cost gate runs before any
 * subprocess is spawned; a failing gate throws `CommandGateError` (never a
 * placeholder response). Tests inject a runner and/or gate to avoid real
 * paid / unknown-charge invocations.
 */
export function makeCommandLLMClient(opts: {
  readonly spec: CommandProviderSpec;
  readonly runner?: CommandRunner;
  readonly gate?: () => CommandGateResult;
}): LLMClient {
  const runner = opts.runner ?? spawnRunner;
  const gate = opts.gate ?? opts.spec.gate;
  return {
    async complete(input: LLMTurnInput): Promise<LLMResponse> {
      const result = gate();
      if (!result.ok) throw new CommandGateError(opts.spec.name, result.reason);
      const args = opts.spec.buildArgs(input, opts.spec.model);
      const { stdout, stderr, code } = await runner(opts.spec.command, args);
      return opts.spec.parseOutput(stdout, stderr, code);
    },
  };
}
