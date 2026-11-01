"use client";

import type { CatalogModel, CatalogTool } from "@/lib/api/types";
import { MODEL_SIZE_LABEL } from "@/lib/labels";
import { type SpecFormValues, toggleTool } from "@/lib/specForm";

const MIN_ITERATIONS = 1;
const MAX_ITERATIONS = 20;

interface SpecFieldsProps {
  values: SpecFormValues;
  models: CatalogModel[];
  tools: CatalogTool[];
  knowledgeBaseId: string | null;
  onChange: (values: SpecFormValues) => void;
}

function renderModelOption(model: CatalogModel) {
  return <option key={model.id} value={model.id}>{model.name} ({MODEL_SIZE_LABEL[model.size]}) — {model.recommended_use}</option>;
}

function ToolCheckbox({ tool, isChecked, onToggle }: { tool: CatalogTool; isChecked: boolean; onToggle: (name: string) => void }) {
  return (
    <label className="flex items-start gap-2 text-sm">
      <input type="checkbox" checked={isChecked} onChange={() => onToggle(tool.name)} className="mt-1" />
      <span><span className="font-mono">{tool.name}</span> <span className="block text-slate-600">{tool.description}</span></span>
    </label>
  );
}

/**
 * Draws the editable fields of a spec.
 *
 * Exists so the form keeps only the saving logic. Models and tools are closed choices, because the
 * platform only accepts entries of the catalogs. The knowledge base is read-only: no endpoint lists
 * the bases to choose from.
 *
 * @param props.values - The current values.
 * @param props.models - The models to choose from.
 * @param props.tools - The tools to choose from.
 * @param props.knowledgeBaseId - The base attached to the spec, if any.
 * @param props.onChange - Called with the new values on every edit.
 * @returns The fields.
 */
export function SpecFields({ values, models, tools, knowledgeBaseId, onChange }: SpecFieldsProps) {
  function renderToolCheckbox(tool: CatalogTool) {
    return <ToolCheckbox key={tool.id} tool={tool} isChecked={values.toolNames.includes(tool.name)} onToggle={(name) => onChange({ ...values, toolNames: toggleTool(values.toolNames, name) })} />;
  }

  return (
    <>
      <label className="field-label">Propósito<textarea required rows={2} value={values.purpose} onChange={(event) => onChange({ ...values, purpose: event.target.value })} className="field-input" /></label>
      <label className="field-label">System prompt<textarea required rows={10} value={values.systemPrompt} onChange={(event) => onChange({ ...values, systemPrompt: event.target.value })} className="field-input font-mono" /></label>
      <label className="field-label">Modelo<select value={values.modelId} onChange={(event) => onChange({ ...values, modelId: event.target.value })} className="field-input">{models.map(renderModelOption)}</select></label>
      <fieldset className="space-y-2"><legend className="field-label">Herramientas</legend>{tools.map(renderToolCheckbox)}</fieldset>
      <p className="text-sm"><span className="font-medium text-slate-700">Base de conocimiento:</span> <span className="font-mono break-all text-slate-600">{knowledgeBaseId ?? "Ninguna"}</span></p>
      <label className="field-label">Guardrails (uno por línea)<textarea rows={4} value={values.guardrailsText} onChange={(event) => onChange({ ...values, guardrailsText: event.target.value })} className="field-input" /></label>
      <label className="field-label">Máximo de iteraciones<input type="number" required min={MIN_ITERATIONS} max={MAX_ITERATIONS} value={values.maxIterations} onChange={(event) => onChange({ ...values, maxIterations: event.target.valueAsNumber })} className="field-input" /></label>
    </>
  );
}
