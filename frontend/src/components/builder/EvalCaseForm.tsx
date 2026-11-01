"use client";

import { type FormEvent, useState } from "react";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { addEvalCase } from "@/lib/api/client";

const EMPTY_CASE = { input: "", expected_behavior: "" };

interface EvalCaseFormProps {
  agentId: string;
  isDisabled: boolean;
  onAdded: () => void;
}

/**
 * Lets a person of the owner area write a test case.
 *
 * Exists because publishing requires these cases: generated ones come from the spec they evaluate,
 * and the generator invents data, like customer numbers, so only a person can say what is useful and
 * cover a query that must succeed with real data.
 *
 * @param props.agentId - The agent the case evaluates.
 * @param props.isDisabled - Whether another action is in progress.
 * @param props.onAdded - Called once the case is stored.
 * @returns The form.
 */
export function EvalCaseForm({ agentId, isDisabled, onAdded }: EvalCaseFormProps) {
  const [values, setValues] = useState(EMPTY_CASE);
  const { isRunning, error, run } = useAsyncAction();

  async function add(): Promise<void> {
    await addEvalCase(agentId, values);
    setValues(EMPTY_CASE);
    onAdded();
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(add);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="card space-y-3">
      <h2 className="font-semibold">Agregar un caso del área dueña</h2>
      <p className="text-sm text-slate-600">Escribe consultas reales de tu área. Los casos generados solo miden si el agente cumple su spec; estos miden si es útil, y son obligatorios para publicar.</p>
      <label className="field-label">Mensaje de prueba<textarea required rows={2} value={values.input} onChange={(event) => setValues({ ...values, input: event.target.value })} className="field-input" /></label>
      <label className="field-label">Qué debería hacer el agente<textarea required rows={2} value={values.expected_behavior} onChange={(event) => setValues({ ...values, expected_behavior: event.target.value })} className="field-input" /></label>
      {error && <ErrorNotice message={error} />}
      <button type="submit" disabled={isDisabled || isRunning} className="button-secondary">{isRunning ? "Agregando…" : "Agregar caso"}</button>
    </form>
  );
}
