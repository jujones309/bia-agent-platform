"use client";

import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { listOrchestrationInventory } from "@/lib/api/client";
import type { OrchestrationInventoryItem, OrchestrationStep } from "@/lib/api/types";
import { orDash } from "@/lib/format";
import { ORCHESTRATION_TYPE_LABEL } from "@/lib/labels";

function renderStep(step: OrchestrationStep) {
  return (
    <li key={step.step_order} className="text-sm">
      <p className="font-medium">
        {step.agent_name} <span className="font-normal text-slate-500">· {orDash(step.model_name)}</span>
      </p>
      {step.tool_names.length > 0 && <p className="text-slate-600">Herramientas: {step.tool_names.join(", ")}</p>}
      <p className="text-slate-600">Recibe: {step.receives_context}</p>
      <p className="text-slate-600">Entrega: {step.delivers_output}</p>
    </li>
  );
}

function renderFlow(flow: OrchestrationInventoryItem) {
  return (
    <section key={flow.id} className="card">
      <h2 className="font-semibold">
        {flow.name} <span className="ml-1 text-xs font-normal text-slate-500">{ORCHESTRATION_TYPE_LABEL[flow.orchestration_type]}</span>
      </h2>
      <p className="mt-1 text-sm text-slate-600">{flow.description}</p>
      <ol className="mt-3 list-decimal space-y-3 pl-5">{flow.steps.map(renderStep)}</ol>
    </section>
  );
}

/**
 * Shows every registered flow with its steps in execution order.
 *
 * Exists as the overview of how agents combine. The flows only describe: no engine executes them.
 *
 * @returns The page content.
 */
export function OrchestrationInventory() {
  const { data, error } = useApiResource(listOrchestrationInventory);
  return (
    <>
      <h1 className="page-title">Orquestación</h1>
      <p className="page-intro">Cómo se combinan los agentes en cada flujo.</p>
      {data ? <div className="space-y-4">{data.map(renderFlow)}</div> : <ResourcePlaceholder error={error} />}
    </>
  );
}
