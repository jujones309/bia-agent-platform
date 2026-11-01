"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { EvalCaseForm } from "@/components/builder/EvalCaseForm";
import { EvalOutcomes } from "@/components/builder/EvalOutcomes";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { generateEvalCases, getEvalReport, publishAgent, retireEvalCase, runEvals } from "@/lib/api/client";
import { AgentStatus, EvalCaseOrigin } from "@/lib/api/types";
import type { Agent, EvalCaseOutcome, EvalReport } from "@/lib/api/types";
import { formatPercent } from "@/lib/format";
import { playgroundPath } from "@/lib/routes";

interface EvalStepProps {
  agent: Agent;
  onBack: () => void;
  onAgentChanged: () => void;
}

const RETIRE_CONFIRMATION = "¿Retirar este caso? Deja de contar para publicar, y sus resultados anteriores se conservan.";

function isGenerated(outcome: EvalCaseOutcome): boolean {
  return outcome.case.origin === EvalCaseOrigin.GENERATED;
}

function describeStanding(report: EvalReport): string {
  return `${report.passed_cases} de ${report.total_cases} casos aprobados (${formatPercent(report.pass_percent)}). Para publicar: ${report.threshold_percent} % sobre al menos ${report.minimum_cases} casos.`;
}

/**
 * Generates the test cases, runs the evals and publishes the agent if it passes the gate.
 *
 * Exists because nothing is published without passing its tests. The button stays disabled below the
 * gate, and the backend decides again when it is pressed.
 *
 * @param props.agent - The agent under review.
 * @param props.onBack - Called to return to the spec.
 * @param props.onAgentChanged - Called when the backend may have changed the status of the agent.
 * @returns The step.
 */
export function EvalStep({ agent, onBack, onAgentChanged }: EvalStepProps) {
  const [isPublished, setIsPublished] = useState(agent.status === AgentStatus.PUBLISHED);
  const loader = useCallback(() => getEvalReport(agent.id), [agent.id]);
  const { data: report, error: loadError, reload } = useApiResource(loader);
  const { isRunning, error, run } = useAsyncAction();

  async function generate(): Promise<void> { await generateEvalCases(agent.id); reload(); }
  async function evaluate(): Promise<void> { await runEvals(agent.id); reload(); onAgentChanged(); }
  async function publish(): Promise<void> { await publishAgent(agent.id); setIsPublished(true); onAgentChanged(); }
  async function retire(caseId: string): Promise<void> { await retireEvalCase(agent.id, caseId); reload(); }

  function handleRetire(caseId: string): void {
    if (window.confirm(RETIRE_CONFIRMATION)) void run(retire.bind(null, caseId));
  }

  if (!report) return <ResourcePlaceholder error={loadError} />;
  return (
    <div className="max-w-5xl space-y-4">
      <div className="card space-y-3">
        <p className="text-sm">{describeStanding(report)}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => onBack()} disabled={isRunning} className="button-secondary">Volver a la spec</button>
          {!report.outcomes.some(isGenerated) && <button type="button" onClick={() => void run(generate)} disabled={isRunning} className="button-secondary">Generar casos</button>}
          <button type="button" onClick={() => void run(evaluate)} disabled={isRunning || report.total_cases === 0} className="button-secondary">Correr evals</button>
          <button type="button" onClick={() => void run(publish)} disabled={isRunning || !report.passes_gate || isPublished} className="button-primary">{isPublished ? "Publicado" : "Publicar"}</button>
        </div>
        {isRunning && <p className="text-sm text-slate-600">Trabajando… Generar casos tarda unos segundos, y una corrida de evals puede tardar varios minutos.</p>}
        {error && <ErrorNotice message={error} />}
        {isPublished && <Link href={playgroundPath(agent.id)} className="text-link text-sm">Probar el agente en el playground</Link>}
      </div>
      <EvalCaseForm agentId={agent.id} isDisabled={isRunning} onAdded={() => reload()} />
      <EvalOutcomes outcomes={report.outcomes} isDisabled={isRunning} onRetire={(caseId) => handleRetire(caseId)} />
    </div>
  );
}
