"use client";

import { type FormEvent, useState } from "react";
import { SpecFields } from "@/components/builder/SpecFields";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { patchAgent } from "@/lib/api/client";
import { AgentStatus } from "@/lib/api/types";
import type { Agent, AgentVersion } from "@/lib/api/types";
import type { AgentReviewData } from "@/lib/loaders";
import { buildSpecPatch, toFormValues } from "@/lib/specForm";

interface SpecFormProps {
  agent: Agent;
  version: AgentVersion;
  review: AgentReviewData;
  onSaved: () => void;
}

/**
 * Lets a person adjust the proposed spec, next to the reasons of the designer.
 *
 * Exists because the person, and not the designer, decides what gets published. Saving without
 * changes creates no version.
 *
 * @param props.agent - The agent under review.
 * @param props.version - The active version the form starts from.
 * @param props.review - The justification and the catalogs and bases to choose from.
 * @param props.onSaved - Called once the spec is saved or nothing needed saving.
 * @returns The form.
 */
export function SpecForm({ agent, version, review, onSaved }: SpecFormProps) {
  const [values, setValues] = useState(() => toFormValues(version.spec));
  const { isRunning, error, run } = useAsyncAction();

  async function save(): Promise<void> {
    const patch = buildSpecPatch(version.spec, values);
    if (Object.keys(patch).length > 0) await patchAgent(agent.id, patch);
    onSaved();
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(save);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="grid max-w-5xl gap-4 lg:grid-cols-3">
      <div className="card space-y-4 lg:col-span-2">
        <SpecFields values={values} models={review.models} tools={review.tools} knowledgeBases={review.knowledgeBases} onChange={(next) => setValues(next)} />
        {agent.status === AgentStatus.PUBLISHED && <p className="text-sm text-amber-800">Si guardas cambios, el agente vuelve a pruebas hasta publicarlo otra vez.</p>}
        {error && <ErrorNotice message={error} />}
        <button type="submit" disabled={isRunning} className="button-primary">{isRunning ? "Guardando…" : "Guardar y continuar a evals"}</button>
      </div>
      <aside className="card h-fit">
        <h2 className="font-semibold">Por qué el diseñador eligió esto</h2>
        <p className="mt-2 text-sm wrap-break-word whitespace-pre-wrap text-slate-600">{review.justification ?? "Este agente no fue propuesto por el diseñador."}</p>
      </aside>
    </form>
  );
}
