import { spawn } from "node:child_process";
import type { LLMClient, LLMTurnInput, LLMResponse } from "@openreel/agent";

/** Result of a spawned command. Tests inject a fake spawner and never reach it. */
export interface SpawnResult {
  readonly stdout: string;
  readonly stderr: string;
  /** Process exit code (0 = success). */
  readonly code: number;
}

/**
 * Injected process spawner. The default uses child_process and is ONLY reached
 * when the cost gate has allowed a live call (see cost-gate.ts / providers.ts);
 * an unverified / paid upstream never reaches the default spawner. Tests inject
 * a fake that returns canned output so the call-form can be exercised without a
 * real (paid / unknown-billing) process call.
 */
export type SpawnFn = (
  command: string,
  args: readonly string[],
  opts: { readonly input?: string; readonly timeoutMs?: number },
) => Promise<SpawnResult>;

/**
 * A command-backed provider spec. `buildArgs` / `stdin` describe how the turn is
 * rendered into CLI input; `parseOutput` turns the command's output into an
 * LLMResponse. A spec is a *call-form description* only — it carries no billing
 * decision (that is the cost gate's job).
 */
export interface ServerManagerSpec {
  readonly command: string;
  /** CLI args for the turn (may include the prompt, or omit it if via stdin). */
  readonly buildArgs: (input: LLMTurnInput) => string[];
  /** Optional stdin payload (e.g. codex reads the prompt from stdin). */
  readonly stdin?: (input: LLMTurnInput) => string;
  /** Parse the command output into an LLMResponse. */
  readonly parseOutput: (result: SpawnResult) => LLMResponse;
}

export interface ServerManagerOptions extends ServerManagerSpec {
  /** Injected spawner (tests); defaults to the real child_process spawn. */
  readonly spawn?: SpawnFn;
  readonly timeoutMs?: number;
}

/**
 * A command-backed LLMClient. It renders the turn to CLI args (+ optional
 * stdin), spawns the command, and parses stdout into an LLMResponse.
 *
 * It performs NO billing decision — that is the cost gate's job. The spawner is
 * injectable so the call-form can be exercised with a fake that returns canned
 * output, without a real (paid / unknown-billing) process call. A live command
 * call only fires when the cost gate has allowed it (an unverified upstream
 * never reaches this class — see providers.ts).
 */
export class ServerManager implements LLMClient {
  private readonly spec: ServerManagerSpec;
  private readonly spawn: SpawnFn;
  private readonly timeoutMs: number;

  constructor(opts: ServerManagerOptions) {
    this.spec = opts;
    this.spawn = opts.spawn ?? defaultSpawn;
    this.timeoutMs = opts.timeoutMs ?? 120_000;
  }

  async complete(input: LLMTurnInput): Promise<LLMResponse> {
    const args = this.spec.buildArgs(input);
    const stdin = this.spec.stdin?.(input);
    const result = await this.spawn(this.spec.command, args, {
      input: stdin,
      timeoutMs: this.timeoutMs,
    });
    return this.spec.parseOutput(result);
  }
}

/**
 * Default spawner: runs the command via child_process. It is only reached when
 * the cost gate has allowed a live call, so it never fires for an unverified /
 * paid upstream in the current (no-live-call) state.
 */
export const defaultSpawn: SpawnFn = async (
  command,
  args,
  opts,
): Promise<SpawnResult> => {
  return new Promise<SpawnResult>((resolve, reject) => {
    const child = spawn(command, args as string[], {
      stdio: ["pipe", "pipe", "pipe"],
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d: Buffer) => {
      stdout += d.toString();
    });
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString();
    });
    child.on("error", (err: Error) => reject(err));
    child.on("close", (code: number | null) => {
      resolve({ stdout, stderr, code: code ?? 1 });
    });
    if (opts.input) {
      child.stdin.write(opts.input);
    }
    child.stdin.end();
  });
};
