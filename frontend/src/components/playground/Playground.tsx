"use client";

import { type FormEvent, useCallback, useState } from "react";
import { ChatTurnView } from "@/components/playground/ChatTurnView";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { type ChatTurn, usePlaygroundChat } from "@/hooks/usePlaygroundChat";
import { getAgentDetail } from "@/lib/api/client";

function renderTurn(turn: ChatTurn, position: number) {
  return <ChatTurnView key={position} turn={turn} />;
}

/**
 * Lets a person try an agent and open the trace of each answer.
 *
 * Exists to see an agent working before trusting it. It says that messages are independent, because
 * the backend receives no history and the look of a chat would suggest otherwise.
 *
 * @param props.agentId - The agent to talk to.
 * @returns The page content.
 */
export function Playground({ agentId }: { agentId: string }) {
  const loader = useCallback(() => getAgentDetail(agentId), [agentId]);
  const { data, error } = useApiResource(loader);
  const { turns, pendingInput, send } = usePlaygroundChat(agentId);
  const [input, setInput] = useState("");

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void send(input);
    setInput("");
  }

  if (!data) return <ResourcePlaceholder error={error} />;
  return (
    <div className="max-w-3xl">
      <h1 className="page-title">{data.agent.name}</h1>
      <p className="page-intro">{data.agent.description} Cada mensaje se responde por separado: el agente no recuerda los anteriores.</p>
      <div className="space-y-4">
        {turns.map(renderTurn)}
        {pendingInput && <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-emerald-700 px-3 py-2 text-sm text-white">{pendingInput}</p>}
        {pendingInput && <p className="text-sm text-slate-500">El agente está respondiendo…</p>}
      </div>
      <form onSubmit={(event) => handleSubmit(event)} className="mt-6 flex items-end gap-2">
        <label className="field-label flex-1">Tu mensaje<input required value={input} onChange={(event) => setInput(event.target.value)} className="field-input" /></label>
        <button type="submit" disabled={pendingInput !== null || input.trim().length === 0} className="button-primary">Enviar</button>
      </form>
    </div>
  );
}
