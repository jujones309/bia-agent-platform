import Link from "next/link";
import { DuplicateVerdict } from "@/lib/api/types";
import type { DuplicateCandidate } from "@/lib/api/types";
import { playgroundPath } from "@/lib/routes";

interface CandidateCardProps {
  candidate: DuplicateCandidate;
  verdict: DuplicateVerdict;
  reason: string;
  onReject: () => void;
}

/**
 * Asks whether an existing agent is the one the person was looking for.
 *
 * Exists because the judge only suggests: the person confirms before reusing or creating.
 *
 * @param props.candidate - The agent that resembles the need.
 * @param props.verdict - Whether it covers the whole need or a part of it.
 * @param props.reason - Why the judge says so.
 * @param props.onReject - Called when the person prefers to create a new agent.
 * @returns The card.
 */
export function CandidateCard({ candidate, verdict, reason, onReject }: CandidateCardProps) {
  const heading = verdict === DuplicateVerdict.EXISTS ? "¿Es este agente?" : "Este agente cubre una parte. ¿Te sirve?";
  return (
    <section className="card space-y-3 border-emerald-300">
      <h2 className="font-semibold">{heading}</h2>
      <div>
        <p className="font-medium">{candidate.name}</p>
        <p className="text-sm text-slate-600">{candidate.description}</p>
      </div>
      <p className="text-sm text-slate-600">{reason}</p>
      <div className="flex flex-wrap gap-2">
        <Link href={playgroundPath(candidate.agent_id)} className="button-primary">Sí, usar este agente</Link>
        <button type="button" onClick={() => onReject()} className="button-secondary">No, crear uno nuevo</button>
      </div>
    </section>
  );
}
