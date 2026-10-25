import { describe, it, expect } from "vitest";
import type { LLMTurnInput } from "@openreel/agent";
import {
  codexGate,
  piGate,
  parseCommandOutput,
  makeCommandLLMClient,
  codexProvider,
  piProvider,
  COMMAND_PROVIDERS,
  type CommandRunner,
} from "./command-llm";

const sampleInput: LLMTurnInput = {
  system: "sys",
  messages: [{ role: "user", content: "Edit the title." }],
  tools: [],
};

describe("codexGate — cost gate never try-runs a paid service", () => {
  it("refuses when no key is configured (registered, not invocable, no placeholder)", () => {
    const r = codexGate();
    expect(r.ok).toBe(false);
    expect(r.reason).toMatch(/not invocable|no placeholder/i);
  });

  it("refuses even when a key IS present (impl side never try-runs paid)", () => {
    const prev = process.env.OPENAI_API_KEY;
    process.env.OPENAI_API_KEY = "sk-live-should-never-be-used";
    try {
      const r = codexGate();
      expect(r.ok).toBe(false);
      expect(r.reason).toMatch(/does not try-run|member-provided/i);
    } finally {
      if (prev === undefined) delete process.env.OPENAI_API_KEY;
      else process.env.OPENAI_API_KEY = prev;
    }
  });
});

describe("piGate — read-only local/LAN verification, no live call", () => {
  it("refuses when reachability is false (never claims verified)", () => {
    // Deterministic in every case: config missing -> false at the config check;
    // config present+valid but not reachable -> false at the reachability check.
    const r = piGate(() => false);
    expect(r.ok).toBe(false);
  });

  it("returns a gate result with a non-empty reason (contract)", () => {
    const r = piGate();
    expect(typeof r.reason).toBe("string");
    expect(r.reason.length).toBeGreaterThan(0);
  });
});

describe("makeCommandLLMClient — cost gate runs before any subprocess", () => {
  it("throws CommandGateError and NEVER spawns when the gate refuses (codex)", async () => {
    let calls = 0;
    const spyRunner: CommandRunner = async () => {
      calls++;
      return { stdout: "should-never-run", stderr: "", code: 0 };
    };
    const client = makeCommandLLMClient({ spec: codexProvider, runner: spyRunner });
    await expect(client.complete(sampleInput)).rejects.toThrow(/codex/);
    expect(calls).toBe(0);
  });

  it("calls the (fake) runner exactly once and parses output when the gate passes", async () => {
    let calls = 0;
    const fakeRunner: CommandRunner = async (command, args) => {
      calls++;
      expect(command).toBe("pi");
      expect(args[0]).toBe("--print");
      return { stdout: "Rendered the edit.", stderr: "", code: 0 };
    };
    const client = makeCommandLLMClient({
      spec: piProvider,
      runner: fakeRunner,
      gate: () => ({ ok: true, reason: "test-gate" }),
    });
    const res = await client.complete(sampleInput);
    expect(calls).toBe(1);
    expect(res.text).toBe("Rendered the edit.");
    expect(res.toolUses).toEqual([]);
    expect(res.stopReason).toBe("end_turn");
  });
});

describe("parseCommandOutput", () => {
  it("throws on a non-zero exit", () => {
    expect(() => parseCommandOutput("", "boom", 1, "pi")).toThrow(/pi exited 1/);
  });

  it("throws on empty output with exit 0", () => {
    expect(() => parseCommandOutput("   ", "", 0, "pi")).toThrow(/no output/);
  });

  it("returns text with end_turn and no fabricated tool calls", () => {
    expect(parseCommandOutput("  hello ", "", 0, "pi")).toEqual({
      text: "hello",
      toolUses: [],
      stopReason: "end_turn",
    });
  });
});

describe("COMMAND_PROVIDERS registry", () => {
  it("registers codex and pi with a gate each", () => {
    expect(Object.keys(COMMAND_PROVIDERS).sort()).toEqual(["codex", "pi"]);
    expect(typeof codexProvider.gate().ok).toBe("boolean");
    expect(typeof piProvider.gate).toBe("function");
  });
});
