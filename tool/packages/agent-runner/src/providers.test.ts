import { describe, it, expect } from "vitest";
import type { LLMTurnInput } from "@openreel/agent";
import {
  buildClient,
  renderPrompt,
  listProviders,
  PROVIDER_DESCRIPTORS,
} from "./providers";
import {
  evaluateCostGate,
  CostGateError,
  type CostGateEvidence,
} from "./cost-gate";
import type { SpawnFn, SpawnResult } from "./server-manager";

function turn(system?: string): LLMTurnInput {
  return {
    system,
    messages: [{ role: "user", content: "Add a fade-in to the first clip." }],
    tools: [],
  };
}

/** A fake spawner that records calls and returns canned output (no real process). */
function fakeSpawn(canned: SpawnResult) {
  const calls: Array<{ command: string; args: string[]; input?: string }> = [];
  const fn: SpawnFn = async (command, args, opts) => {
    calls.push({ command, args: [...args], input: opts.input });
    return canned;
  };
  return { fn, calls };
}

/** A "verified" upstream (only a future task may supply this; never from a probe). */
const VERIFIED: CostGateEvidence = {
  probes: ["member-ruling: upstream confirmed zero-pay/local"],
  upstreamBillingVerified: true,
  basis: "member-ruling",
  recordedAt: "2026-10-24T00:00:00Z",
};

// ---- cost gate (pure decision) ---------------------------------------------

describe("evaluateCostGate", () => {
  it("allows an HTTP provider with a BYOK key", () => {
    expect(
      evaluateCostGate({
        provider: "anthropic",
        transport: "http",
        hasApiKey: true,
      }),
    ).toMatchObject({ allowed: true, reason: "allowed" });
  });

  it("rejects an HTTP provider with no key", () => {
    expect(
      evaluateCostGate({
        provider: "openai",
        transport: "http",
        hasApiKey: false,
      }),
    ).toMatchObject({ allowed: false, reason: "no-key" });
  });

  it("rejects codex when the upstream is unverified (no key)", () => {
    const d = evaluateCostGate({
      provider: "codex",
      transport: "command",
      hasApiKey: false,
    });
    expect(d).toMatchObject({ allowed: false, reason: "unverified-upstream" });
    expect(d.message).toContain("待验证");
  });

  it("rejects pi when the upstream is unverified", () => {
    expect(
      evaluateCostGate({
        provider: "pi",
        transport: "command",
        hasApiKey: false,
      }),
    ).toMatchObject({ allowed: false, reason: "unverified-upstream" });
  });

  it("rejects codex even when verified if there is no key from formal settings", () => {
    expect(
      evaluateCostGate({
        provider: "codex",
        transport: "command",
        hasApiKey: false,
        upstreamVerification: VERIFIED,
      }),
    ).toMatchObject({ allowed: false, reason: "no-key" });
  });

  it("allows codex when verified AND a key is present", () => {
    expect(
      evaluateCostGate({
        provider: "codex",
        transport: "command",
        hasApiKey: true,
        upstreamVerification: VERIFIED,
      }),
    ).toMatchObject({ allowed: true, reason: "allowed" });
  });

  it("allows pi when verified (key is proxy-managed)", () => {
    expect(
      evaluateCostGate({
        provider: "pi",
        transport: "command",
        hasApiKey: false,
        upstreamVerification: VERIFIED,
      }),
    ).toMatchObject({ allowed: true, reason: "allowed" });
  });
});

// ---- provider registry + cost gate integration -----------------------------

describe("buildClient", () => {
  it("registers all four providers with the documented gateways", () => {
    expect(listProviders()).toEqual(
      expect.arrayContaining(["anthropic", "openai", "codex", "pi"]),
    );
    expect(PROVIDER_DESCRIPTORS.codex.gateway).toBe(
      "http://127.0.0.1:15721/v1",
    );
    expect(PROVIDER_DESCRIPTORS.codex.model).toBe("qwen3.8-27b-office");
    expect(PROVIDER_DESCRIPTORS.pi.gateway).toBe("http://192.168.31.154:10013");
    expect(PROVIDER_DESCRIPTORS.pi.model).toBe("qwen3.8-27b-office");
  });

  it("rejects a command provider's live call when unverified — and never spawns", async () => {
    const { fn, calls } = fakeSpawn({ stdout: "", stderr: "", code: 0 });
    const client = buildClient({ provider: "codex", spawn: fn });
    await expect(client.complete(turn())).rejects.toThrow(CostGateError);
    // The hard boundary: an unverified upstream is NOT called.
    expect(calls).toHaveLength(0);
  });

  it("rejects pi's live call when unverified", async () => {
    const { fn, calls } = fakeSpawn({ stdout: "", stderr: "", code: 0 });
    const client = buildClient({ provider: "pi", spawn: fn });
    await expect(client.complete(turn())).rejects.toThrow(CostGateError);
    expect(calls).toHaveLength(0);
  });

  it("throws CostGateError for an HTTP provider with no key", () => {
    expect(() => buildClient({ provider: "anthropic", apiKey: "" })).toThrow(
      CostGateError,
    );
  });
});

// ---- command call-form (only when the gate allows) -----------------------

describe("command call-form (gated, via injected fake spawner)", () => {
  it("codex renders the prompt to stdin and parses JSONL output", async () => {
    const canned: SpawnResult = {
      stdout:
        '{"type":"message","content":"Working..."}\n' +
        '{"type":"message","content":"Done, added a fade-in."}\n' +
        '{"usage":{"input_tokens":10,"output_tokens":5}}\n',
      stderr: "",
      code: 0,
    };
    const { fn, calls } = fakeSpawn(canned);
    // A future "verified" state lets the call fire; the call-form is exercised
    // here with a fake spawner — no real (paid/unknown-billing) process call.
    const client = buildClient({
      provider: "codex",
      upstreamVerification: VERIFIED,
      hasApiKey: true,
      spawn: fn,
    });
    const res = await client.complete(turn("You are a video editing assistant."));
    expect(res.text).toBe("Done, added a fade-in.");
    expect(res.stopReason).toBe("end_turn");
    expect(res.toolUses).toEqual([]);
    expect(res.usage).toEqual({ inputTokens: 10, outputTokens: 5 });
    // call-form: codex exec --json -m <model>, prompt via stdin
    expect(calls[0].command).toBe("codex");
    expect(calls[0].args).toEqual(["exec", "--json", "-m", "qwen3.8-27b-office"]);
    expect(calls[0].input).toContain("fade-in");
  });

  it("pi passes the prompt as a positional arg and parses JSON output", async () => {
    const canned: SpawnResult = {
      stdout: JSON.stringify({
        choices: [
          {
            message: {
              content: [
                { type: "text", text: "I edited the timeline." },
              ],
            },
          },
        ],
        usage: { prompt_tokens: 7, completion_tokens: 3 },
      }),
      stderr: "",
      code: 0,
    };
    const { fn, calls } = fakeSpawn(canned);
    const client = buildClient({
      provider: "pi",
      upstreamVerification: VERIFIED,
      spawn: fn,
    });
    const res = await client.complete(turn());
    expect(res.text).toBe("I edited the timeline.");
    expect(res.usage).toEqual({ inputTokens: 7, outputTokens: 3 });
    expect(calls[0].command).toBe("pi");
    expect(calls[0].args[0]).toBe("--print");
    expect(calls[0].args).toContain("--mode");
    expect(calls[0].args).toContain("json");
    expect(calls[0].args).toContain("qwen3.8-27b-office");
  });

  it("throws (does not silently blank) on a non-zero command exit", async () => {
    const { fn } = fakeSpawn({ stdout: "", stderr: "boom", code: 1 });
    const client = buildClient({
      provider: "pi",
      upstreamVerification: VERIFIED,
      spawn: fn,
    });
    await expect(client.complete(turn())).rejects.toThrow(/pi exited with code 1/);
  });
});

// ---- renderPrompt ---------------------------------------------------------

describe("renderPrompt", () => {
  it("renders system + messages into a single prompt", () => {
    const text = renderPrompt(
      turn("You are a video editing assistant."),
    );
    expect(text).toContain("You are a video editing assistant.");
    expect(text).toContain("User:");
    expect(text).toContain("fade-in");
  });
});
