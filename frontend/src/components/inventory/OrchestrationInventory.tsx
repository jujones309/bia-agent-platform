"use client";

import { AgentStatusBadge } from "@/components/ui/Badge";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { listOrchestrationInventory, retireOrchestration } from "@/lib/api/client";
import type { OrchestrationInventoryItem, OrchestrationStep } from "@/lib/api/types";
import { orDash } from "@/lib/format";
import { ORCHESTRATION_TYPE_LABEL } from "@/lib/labels";

const RETIRE_CONFIRMATION = "¿Retirar este flujo? Deja de aparecer aquí; sus agentes no cambian y volver a publicarlos no lo trae de vuelta.";

function renderStep(step: OrchestrationStep) {
  return (
    <li key={step.step_order} className="text-sm">
      <p className="font-medium">
        {step.agent_name} <span className="font-normal text-slate-500">· {orDash(step.model_name)}</span> <AgentStatusBadge status={step.agent_status} />
      </p>
      {step.tool_names.length > 0 && <p className="text-slate-600">Herramientas: {step.tool_names.join(", ")}</p>}
      <p className="text-slate-600">Recibe: {step.receives_context}</p>
      <p className="text-slate-600">Entrega: {step.delivers_output}</p>
    </li>
  );
}

interface FlowCardProps {
  flow: OrchestrationInventoryItem;
  isDisabled: boolean;
  onRetire: (flowId: string) => void;
}

function FlowCard({ flow, isDisabled, onRetire }: FlowCardProps) {
  return (
    <section className="card">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-semibold">
          {flow.name} <span className="ml-1 text-xs font-normal text-slate-500">{ORCHESTRATION_TYPE_LABEL[flow.orchestration_type]}</span>
        </h2>
        {!flow.is_system && <button type="button" onClick={() => onRetire(flow.id)} disabled={isDisabled} className="text-link text-sm disabled:text-slate-400">Retirar</button>}
      </div>
      <p className="mt-1 text-sm text-slate-600">{flow.description}</p>
      <ol className="mt-3 list-decimal space-y-3 pl-5">{flow.steps.map(renderStep)}</ol>
    </section>
  );
}

/**
 * Shows every registered flow with its steps in execution order.
 *
 * Exists as the overview of how agents combine. The flows only describe: no engine executes them, so
 * retiring one changes nothing about its agents. The flow of the platform cannot be retired.
 *
 * @returns The page content.
 */
export function OrchestrationInventory() {
  const { data, error, reload } = useApiResource(listOrchestrationInventory);
  const retirement = useAsyncAction();

  async function retire(flowId: string): Promise<void> { await retireOrchestration(flowId); reload(); }

  function handleRetire(flowId: string): void {
    if (window.confirm(RETIRE_CONFIRMATION)) void retirement.run(retire.bind(null, flowId));
  }

  function renderFlow(flow: OrchestrationInventoryItem) {
    return <FlowCard key={flow.id} flow={flow} isDisabled={retirement.isRunning} onRetire={(flowId) => handleRetire(flowId)} />;
  }

  return (
    <>
      <h1 className="page-title">Orquestación</h1>
      <p className="page-intro">Cómo se combinan los agentes en cada flujo.</p>
      {retirement.error && <div className="mb-4"><ErrorNotice message={retirement.error} /></div>}
      {data ? <div className="space-y-4">{data.map(renderFlow)}</div> : <ResourcePlaceholder error={error} />}
    </>
  );
}
