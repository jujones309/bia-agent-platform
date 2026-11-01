import type { ReactNode } from "react";
import { AgentStatus, EvalVerdict, RunStatus } from "@/lib/api/types";
import { AGENT_STATUS_LABEL, EVAL_VERDICT_LABEL, RUN_STATUS_LABEL } from "@/lib/labels";

const Tone = {
  NEUTRAL: "bg-slate-100 text-slate-700",
  PROGRESS: "bg-amber-100 text-amber-800",
  SUCCESS: "bg-emerald-100 text-emerald-800",
  DANGER: "bg-red-100 text-red-800",
} as const;
type Tone = (typeof Tone)[keyof typeof Tone];

const AGENT_STATUS_TONE: Record<AgentStatus, Tone> = {
  [AgentStatus.DRAFT]: Tone.NEUTRAL,
  [AgentStatus.TESTING]: Tone.PROGRESS,
  [AgentStatus.PUBLISHED]: Tone.SUCCESS,
  [AgentStatus.ARCHIVED]: Tone.NEUTRAL,
};

const RUN_STATUS_TONE: Record<RunStatus, Tone> = {
  [RunStatus.RUNNING]: Tone.PROGRESS,
  [RunStatus.SUCCEEDED]: Tone.SUCCESS,
  [RunStatus.FAILED]: Tone.DANGER,
};

const EVAL_VERDICT_TONE: Record<EvalVerdict, Tone> = {
  [EvalVerdict.PASS]: Tone.SUCCESS,
  [EvalVerdict.FAIL]: Tone.DANGER,
};

function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${tone}`}>{children}</span>;
}

/**
 * Shows the lifecycle stage of an agent.
 *
 * @param props.status - The stage.
 * @returns The badge.
 */
export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  return <Badge tone={AGENT_STATUS_TONE[status]}>{AGENT_STATUS_LABEL[status]}</Badge>;
}

/**
 * Shows how a run ended.
 *
 * @param props.status - The state of the run.
 * @returns The badge.
 */
export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <Badge tone={RUN_STATUS_TONE[status]}>{RUN_STATUS_LABEL[status]}</Badge>;
}

/**
 * Shows the decision of the eval judge.
 *
 * @param props.verdict - The decision.
 * @returns The badge.
 */
export function EvalVerdictBadge({ verdict }: { verdict: EvalVerdict }) {
  return <Badge tone={EVAL_VERDICT_TONE[verdict]}>{EVAL_VERDICT_LABEL[verdict]}</Badge>;
}

/**
 * Shows that a case still has no result on the active version, which counts against the gate.
 *
 * @returns The badge.
 */
export function PendingBadge() {
  return <Badge tone={Tone.NEUTRAL}>Pendiente</Badge>;
}
