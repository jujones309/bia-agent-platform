"use client";

import { type FormEvent, useState } from "react";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { updateAgentIdentity } from "@/lib/api/client";
import type { Agent } from "@/lib/api/types";
import { buildIdentityPatch, toIdentityValues } from "@/lib/identityForm";

/**
 * Lets a person change the name, description and area of an agent.
 *
 * Exists because these are not part of the spec. The description is what the duplicate search compares,
 * so the backend embeds it again when it changes. Saving without changes calls nothing.
 *
 * @param props.agent - The agent to edit.
 * @param props.onSaved - Called once the change is stored.
 * @returns The form.
 */
export function AgentIdentityForm({ agent, onSaved }: { agent: Agent; onSaved: () => void }) {
  const [values, setValues] = useState(() => toIdentityValues(agent));
  const { isRunning, error, run } = useAsyncAction();
  const patch = buildIdentityPatch(agent, values);
  const hasChanges = Object.keys(patch).length > 0;

  async function save(): Promise<void> {
    await updateAgentIdentity(agent.id, patch);
    onSaved();
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(save);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="card space-y-3">
      <h2 className="font-semibold">Identidad</h2>
      <label className="field-label">Nombre<input required value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} className="field-input" /></label>
      <label className="field-label">Descripción<textarea required rows={3} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} className="field-input" /></label>
      <label className="field-label">Área<input required value={values.ownerArea} onChange={(event) => setValues({ ...values, ownerArea: event.target.value })} className="field-input" /></label>
      {error && <ErrorNotice message={error} />}
      <button type="submit" disabled={isRunning || !hasChanges} className="button-primary">{isRunning ? "Guardando…" : "Guardar identidad"}</button>
    </form>
  );
}
