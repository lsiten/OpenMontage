/**
 * Cost gate: the single decision of whether a provider may make a LIVE call.
 *
 * This is the hard boundary of the task. The gate is a PURE decision — it does
 * NOT spawn a process, make a network call, configure a key, or echo a key.
 * Registration of a provider (in providers.ts) only describes its call-form;
 * the gate decides whether that call-form may actually fire.
 *
 * Hard boundary (violating any = failing the task):
 *  - A paid / unknown-billing service is never called on a trial.
 *  - An upstream whose billing / authorization is unverified is never called;
 *    it is recorded as 待验证 / 未覆盖, and we must NOT claim "已零付费接入".
 *  - API keys come from the member's formal settings UI; the implementation
 *    never configures, echoes, or processes them here.
 *
 * Why a read-only probe cannot approve a live call: the codex / pi gateways are
 * OpenAI-compatible proxies (local sub2api 127.0.0.1:15721; LAN
 * 192.168.31.154:10013) that forward to an upstream. sub2api distributes by
 * subscription quota, so the upstream may be a paid subscription. A read-only
 * probe (TCP / /v1/models / /health) confirms reachability, NOT billing — so an
 * unverified upstream is rejected, not called, and never claimed as zero-pay.
 */

export type TransportKind = "http" | "command";

export interface CostGateEvidence {
  /** What was actually probed (command + exit + observed result). */
  readonly probes: readonly string[];
  /** Whether upstream billing / authorization is confirmed zero-pay / local. */
  readonly upstreamBillingVerified: boolean;
  /** How the billing was determined. */
  readonly basis: "member-ruling" | "read-only-probe" | "unverified";
  /** When the evidence was recorded (ISO timestamp). */
  readonly recordedAt: string;
}

export type CostGateReason =
  | "allowed"
  | "no-key"
  | "unverified-upstream"
  | "unknown-provider";

export interface CostGateDecision {
  /** True only when a live call is permitted. */
  readonly allowed: boolean;
  readonly reason: CostGateReason;
  /** Human-readable explanation (safe to log; never contains a key). */
  readonly message: string;
}

export interface CostGateInput {
  readonly provider: string;
  readonly transport: TransportKind;
  /** Non-empty key supplied by the member's formal settings (never echoed). */
  readonly hasApiKey: boolean;
  /** Upstream billing verification; absent = unverified. */
  readonly upstreamVerification?: CostGateEvidence;
}

/**
 * Decide whether a live call is allowed.
 *  - http (BYOK): allowed iff a key is present.
 *  - command: allowed iff the upstream billing is VERIFIED. A read-only probe
 *    cannot confirm a proxy's downstream billing, so unverified = rejected.
 *    codex additionally requires a key (from the member's formal settings);
 *    pi's key is proxy-managed, so pi is gated only by upstream verification.
 */
export function evaluateCostGate(input: CostGateInput): CostGateDecision {
  if (input.transport === "http") {
    return input.hasApiKey
      ? {
          allowed: true,
          reason: "allowed",
          message: `${input.provider}: BYOK key present.`,
        }
      : {
          allowed: false,
          reason: "no-key",
          message: `${input.provider}: no API key (BYOK required).`,
        };
  }
  // command
  if (input.upstreamVerification?.upstreamBillingVerified) {
    if (input.provider === "codex" && !input.hasApiKey) {
      return {
        allowed: false,
        reason: "no-key",
        message: `${input.provider}: upstream verified but no key from formal settings; engine registers only, does not call.`,
      };
    }
    return {
      allowed: true,
      reason: "allowed",
      message: `${input.provider}: upstream billing verified; live call permitted.`,
    };
  }
  const extra =
    input.provider === "codex" && !input.hasApiKey
      ? " No key from formal settings (engine registers only, does not call)."
      : "";
  return {
    allowed: false,
    reason: "unverified-upstream",
    message: `${input.provider}: upstream billing / authorization not verified (待验证 / 未覆盖). Not connected; not claimed as zero-pay integrated.${extra}`,
  };
}

/** Thrown when a gated client is called but the cost gate rejected it. */
export class CostGateError extends Error {
  constructor(readonly decision: CostGateDecision) {
    super(`Cost gate rejected (${decision.reason}): ${decision.message}`);
    this.name = "CostGateError";
  }
}
