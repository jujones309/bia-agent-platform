import { DataTable } from "@/components/ui/DataTable";
import type { CatalogModel, CatalogTool, RunStep } from "@/lib/api/types";
import { findName, formatCost, formatCount, formatLatency, orDash } from "@/lib/format";
import { STEP_TYPE_LABEL } from "@/lib/labels";

const HEADERS = ["#", "Tipo", "Modelo", "Herramienta", "Tokens (entrada / salida)", "Costo", "Latencia", "Detalle"];

interface RunStepsProps {
  steps: RunStep[];
  models: CatalogModel[];
  tools: CatalogTool[];
}

function StepDetail({ step }: { step: RunStep }) {
  return (
    <details>
      <summary className="cursor-pointer text-xs">Ver</summary>
      <pre className="mt-1 max-h-64 max-w-md overflow-auto rounded bg-slate-100 p-2 text-xs">{JSON.stringify({ input: step.input, output: step.output }, null, 2)}</pre>
      {step.error && <p className="mt-1 text-xs text-red-800">{step.error}</p>}
    </details>
  );
}

/**
 * Shows the steps of a run with their type, model, tokens, cost and latency.
 *
 * Exists to make visible where an answer spent its time and money. A step that failed says so in its
 * row, because failures of tools do not fail the run.
 *
 * @param props.steps - The steps, in execution order.
 * @param props.models - The catalog, to name the models.
 * @param props.tools - The catalog, to name the tools.
 * @returns The table.
 */
export function RunSteps({ steps, models, tools }: RunStepsProps) {
  function renderStep(step: RunStep) {
    return (
      <tr key={step.id} className={`align-top ${step.error ? "bg-red-50" : ""}`}>
        <td>{step.step_order}</td>
        <td className="whitespace-nowrap">{STEP_TYPE_LABEL[step.step_type]}{step.error && " (error)"}</td>
        <td className="whitespace-nowrap">{orDash(findName(models, step.model_id))}</td>
        <td className="font-mono whitespace-nowrap">{orDash(findName(tools, step.tool_id))}</td>
        <td className="whitespace-nowrap">{formatCount(step.input_tokens)} / {formatCount(step.output_tokens)}</td>
        <td className="whitespace-nowrap">{formatCost(step.cost)}</td>
        <td className="whitespace-nowrap">{formatLatency(step.latency_ms)}</td>
        <td><StepDetail step={step} /></td>
      </tr>
    );
  }
  return <DataTable headers={HEADERS}>{steps.map(renderStep)}</DataTable>;
}
