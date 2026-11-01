"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { proposeAgent } from "@/lib/api/client";
import { agentReviewPath } from "@/lib/routes";

/**
 * Asks who will own the agent and has the designer propose it.
 *
 * Exists because the designer decides the spec but cannot know whose agent it is. The backend creates
 * the draft, so the next step lives on its own page and survives a reload.
 *
 * @param props.description - The need to design for.
 * @returns The form; on success it navigates to the review of the new agent.
 */
export function ProposeForm({ description }: { description: string }) {
  const router = useRouter();
  const [ownerArea, setOwnerArea] = useState("");
  const [creator, setCreator] = useState("");
  const { isRunning, error, run } = useAsyncAction();

  async function propose(): Promise<void> {
    const proposed = await proposeAgent({ description, owner_area: ownerArea, creator });
    router.push(agentReviewPath(proposed.agent.agent.id));
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(propose);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="card space-y-3">
      <label className="field-label">
        Área dueña
        <input required value={ownerArea} onChange={(event) => setOwnerArea(event.target.value)} className="field-input" />
      </label>
      <label className="field-label">
        Quién lo crea
        <input required value={creator} onChange={(event) => setCreator(event.target.value)} className="field-input" />
      </label>
      {error && <ErrorNotice message={error} />}
      <button type="submit" disabled={isRunning} className="button-primary">
        {isRunning ? "Diseñando el agente…" : "Proponer agente"}
      </button>
    </form>
  );
}
