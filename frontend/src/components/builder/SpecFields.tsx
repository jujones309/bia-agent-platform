"use client";

import Link from "next/link";
import { KNOWLEDGE_TOOL_NAME } from "@/lib/api/types";
import type { CatalogModel, CatalogTool, KnowledgeBase } from "@/lib/api/types";
import { MODEL_SIZE_LABEL } from "@/lib/labels";
import { Route } from "@/lib/routes";
import { type SpecFormValues, withKnowledgeBase, withToggledTool } from "@/lib/specForm";

const MIN_ITERATIONS = 1;
const MAX_ITERATIONS = 20;

interface SpecFieldsProps {
  values: SpecFormValues;
  models: CatalogModel[];
  tools: CatalogTool[];
  knowledgeBases: KnowledgeBase[];
  onChange: (values: SpecFormValues) => void;
}

function renderModelOption(model: CatalogModel) {
  return <option key={model.id} value={model.id}>{model.name} ({MODEL_SIZE_LABEL[model.size]}) — {model.recommended_use}</option>;
}

function renderKnowledgeBaseOption(base: KnowledgeBase) {
  return <option key={base.id} value={base.id}>{base.name} — {base.description}</option>;
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
 * Exists so the form keeps only the saving logic. Models, tools and bases are closed choices, because
 * the platform only accepts what exists. Choosing a base also selects the tool that reads it.
 *
 * @param props.values - The current values.
 * @param props.models - The models to choose from.
 * @param props.tools - The tools to choose from.
 * @param props.knowledgeBases - The bases to choose from.
 * @param props.onChange - Called with the new values on every edit.
 * @returns The fields.
 */
export function SpecFields({ values, models, tools, knowledgeBases, onChange }: SpecFieldsProps) {
  function renderToolCheckbox(tool: CatalogTool) {
    return <ToolCheckbox key={tool.id} tool={tool} isChecked={values.toolNames.includes(tool.name)} onToggle={(name) => onChange(withToggledTool(values, name))} />;
  }

  return (
    <>
      <label className="field-label">Propósito<textarea required rows={2} value={values.purpose} onChange={(event) => onChange({ ...values, purpose: event.target.value })} className="field-input" /></label>
      <label className="field-label">System prompt<textarea required rows={10} value={values.systemPrompt} onChange={(event) => onChange({ ...values, systemPrompt: event.target.value })} className="field-input font-mono" /></label>
      <label className="field-label">Modelo<select value={values.modelId} onChange={(event) => onChange({ ...values, modelId: event.target.value })} className="field-input">{models.map(renderModelOption)}</select></label>
      <fieldset className="space-y-2"><legend className="field-label">Herramientas</legend>{tools.map(renderToolCheckbox)}</fieldset>
      <label className="field-label">Base de conocimiento
        <select required={values.toolNames.includes(KNOWLEDGE_TOOL_NAME)} value={values.knowledgeBaseId ?? ""} onChange={(event) => onChange(withKnowledgeBase(values, event.target.value || null))} className="field-input">
          <option value="">Ninguna</option>
          {knowledgeBases.map(renderKnowledgeBaseOption)}
        </select>
      </label>
      <p className="text-sm text-slate-600">Las bases se crean y se llenan en <Link href={Route.KNOWLEDGE} className="text-link">Conocimiento</Link>.</p>
      <label className="field-label">Guardrails (uno por línea)<textarea rows={4} value={values.guardrailsText} onChange={(event) => onChange({ ...values, guardrailsText: event.target.value })} className="field-input" /></label>
      <label className="field-label">Máximo de iteraciones<input type="number" required min={MIN_ITERATIONS} max={MAX_ITERATIONS} value={values.maxIterations} onChange={(event) => onChange({ ...values, maxIterations: event.target.valueAsNumber })} className="field-input" /></label>
    </>
  );
}
