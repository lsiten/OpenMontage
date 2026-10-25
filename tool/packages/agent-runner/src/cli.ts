#!/usr/bin/env node
import process from "node:process";
import { runHeadlessEditFile } from "./run";
import { type ProviderName, PROVIDER_DESCRIPTORS } from "./providers";
import { evaluateCostGate, CostGateError } from "./cost-gate";

interface CliArgs {
  project?: string;
  prompt?: string;
  provider: ProviderName;
  model?: string;
  out?: string;
  dryRun: boolean;
}

const PROVIDER_NAMES: ProviderName[] = ["anthropic", "openai", "codex", "pi"];

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = { provider: "anthropic", dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = (): string => argv[++i] ?? "";
    switch (arg) {
      case "--project":
      case "-p":
        args.project = next();
        break;
      case "--prompt":
      case "-m":
        args.prompt = next();
        break;
      case "--provider": {
        // Capture the value once: calling next() twice would swallow the
        // following flag (e.g. --project) and break parsing.
        const name = next();
        args.provider = (PROVIDER_NAMES as string[]).includes(name)
          ? (name as ProviderName)
          : "anthropic";
        break;
      }
      case "--model":
        args.model = next();
        break;
      case "--out":
      case "-o":
        args.out = next();
        break;
      case "--dry-run":
        args.dryRun = true;
        break;
      default:
        break;
    }
  }
  return args;
}

/**
 * BYOK key resolution. Only HTTP providers take a key from the environment
 * (never stored/logged). Command providers (codex/pi) take NO key here: codex's
 * key comes from the member's formal settings UI and pi's is proxy-managed, so
 * the cost gate (not this CLI) decides whether a live call may fire.
 */
function resolveApiKey(provider: ProviderName): {
  apiKey: string;
  hasApiKey: boolean;
} {
  if (provider === "anthropic" || provider === "openai") {
    const key =
      process.env.OPENREEL_API_KEY ??
      (provider === "anthropic"
        ? process.env.ANTHROPIC_API_KEY
        : process.env.OPENAI_API_KEY) ??
      "";
    return { apiKey: key, hasApiKey: key.length > 0 };
  }
  return { apiKey: "", hasApiKey: false };
}

const USAGE = `openreel-agent — headless project editing

Usage:
  openreel-agent --project <file.json> --prompt "<instruction>" [options]

Options:
  -p, --project <path>   Project JSON to edit (required)
  -m, --prompt  <text>   Natural-language editing instruction (required)
      --provider <name>  anthropic | openai | codex | pi (default: anthropic)
      --model <id>       Model id (default: provider default)
  -o, --out <path>       Output path (default: edit in place)
      --dry-run          Plan without applying mutations

HTTP key (never stored): OPENREEL_API_KEY, or ANTHROPIC_API_KEY / OPENAI_API_KEY.
codex/pi: no key here (codex key from formal settings; pi is proxy-managed).
          A live call fires only when the cost gate allows it (upstream billing
          verified); an unverified upstream is rejected, not called.`;

/**
 * Up-front cost-gate check. This is what makes the gate visible to the operator:
 * runTurn swallows complete() errors into stoppedReason="error", so the gate
 * must be evaluated BEFORE the turn. A rejection here is the correct, expected
 * outcome — not an error — so it exits 2 (not 1) and does not run the turn.
 */
function assertGate(
  provider: ProviderName,
  hasApiKey: boolean,
): void {
  const decision = evaluateCostGate({
    provider,
    transport: PROVIDER_DESCRIPTORS[provider].transport,
    hasApiKey,
    // upstreamVerification absent = unverified → command providers are rejected.
  });
  if (decision.allowed) return;
  process.stderr.write(`${decision.message}\n`);
  process.stderr.write(
    "Refused by the cost gate; the provider is registered but not called. No live call was made.\n",
  );
  // HTTP no-key is an operator config error (1); a command gate rejection is
  // the expected, correct outcome (2).
  process.exit(decision.reason === "no-key" ? 1 : 2);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (!args.project || !args.prompt) {
    process.stdout.write(`${USAGE}\n`);
    process.exit(args.project || args.prompt ? 1 : 0);
  }
  const { apiKey, hasApiKey } = resolveApiKey(args.provider);

  // HTTP requires a BYOK key; command providers have none here (gate decides).
  assertGate(args.provider, hasApiKey);

  const model = args.model ?? PROVIDER_DESCRIPTORS[args.provider].model;
  try {
    const { result, saved } = await runHeadlessEditFile({
      projectPath: args.project,
      prompt: args.prompt,
      provider: args.provider,
      model,
      apiKey,
      hasApiKey,
      outPath: args.out,
      dryRun: args.dryRun,
    });
    const usage = `${result.usage.inputTokens} in / ${result.usage.outputTokens} out tokens`;
    process.stdout.write(
      `Done (${result.stoppedReason}). ${result.toolCalls} tool call(s), ${usage}.\n` +
        (saved
          ? `Saved to ${args.out ?? args.project}.\n`
          : `Not saved${args.dryRun ? " (dry-run)" : result.stoppedReason === "error" ? " (turn errored)" : ""}.\n`),
    );
    process.exit(result.stoppedReason === "error" ? 1 : 0);
  } catch (error) {
    // A CostGateError here is unexpected (assertGate runs first); report it.
    if (error instanceof CostGateError) {
      process.stderr.write(`${error.decision.message}\n`);
      process.exit(2);
    }
    process.stderr.write(
      `Headless run failed: ${error instanceof Error ? error.message : String(error)}\n`,
    );
    process.exit(1);
  }
}

if (require.main === module) {
  void main();
}
