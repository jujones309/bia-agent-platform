"use client";

import type { FormEvent } from "react";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { checkDuplicates } from "@/lib/api/client";
import type { DuplicateCheckResult } from "@/lib/api/types";

interface DuplicateCheckFormProps {
  description: string;
  onDescriptionChange: (description: string) => void;
  onChecked: (result: DuplicateCheckResult) => void;
}

/**
 * Asks for the need and checks it against the published agents.
 *
 * @param props.description - The need written so far.
 * @param props.onDescriptionChange - Called on every edit.
 * @param props.onChecked - Called with the verdict of the check.
 * @returns The form.
 */
export function DuplicateCheckForm({ description, onDescriptionChange, onChecked }: DuplicateCheckFormProps) {
  const { isRunning, error, run } = useAsyncAction();

  async function checkDescription(): Promise<void> {
    onChecked(await checkDuplicates(description));
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(checkDescription);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="card space-y-3">
      <label className="field-label">
        ¿Qué necesitas que haga el agente?
        <textarea required rows={4} value={description} onChange={(event) => onDescriptionChange(event.target.value)} className="field-input" />
      </label>
      {error && <ErrorNotice message={error} />}
      <button type="submit" disabled={isRunning || description.trim().length === 0} className="button-primary">
        {isRunning ? "Buscando…" : "Buscar agentes parecidos"}
      </button>
    </form>
  );
}
