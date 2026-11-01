"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useState } from "react";
import { ChatTurnView } from "@/components/playground/ChatTurnView";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { type ChatTurn, usePlaygroundChat } from "@/hooks/usePlaygroundChat";
import { getAgentDetail } from "@/lib/api/client";
import { runPath } from "@/lib/routes";

function renderTurn(turn: ChatTurn, position: number) {
  return <ChatTurnView key={position} turn={turn} />;
}

/**
 * Lets a person hold a conversation with an agent, finish it and open its trace.
 *
 * Exists to see an agent working before trusting it. It says how memory works, because a conversation
 * stays open until the person finishes it, and the next one starts without remembering the previous.
 *
 * @param props.agentId - The agent to talk to.
 * @returns The page content.
 */
export function Playground({ agentId }: { agentId: string }) {
  const loader = useCallback(() => getAgentDetail(agentId), [agentId]);
  const { data, error } = useApiResource(loader);
  const { turns, pendingInput, runId, finishedRunId, finishError, finishing, send, finish } = usePlaygroundChat(agentId);
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
      <p className="page-intro">{data.agent.description} El agente recuerda la conversación hasta que la finalices; la siguiente empieza en un run nuevo, sin esa memoria.</p>
      {finishedRunId && <p className="mb-4 text-sm text-slate-500">Conversación finalizada. <Link href={runPath(finishedRunId)} className="text-link">Ver su traza</Link></p>}
      <div className="space-y-4">
        {turns.map(renderTurn)}
        {pendingInput && <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-emerald-700 px-3 py-2 text-sm text-white">{pendingInput}</p>}
        {pendingInput && <p className="text-sm text-slate-500">El agente está respondiendo…</p>}
      </div>
      <form onSubmit={(event) => handleSubmit(event)} className="mt-6 flex items-end gap-2">
        <label className="field-label flex-1">Tu mensaje<input required value={input} onChange={(event) => setInput(event.target.value)} className="field-input" /></label>
        <button type="submit" disabled={pendingInput !== null || input.trim().length === 0} className="button-primary">Enviar</button>
        {runId && <button type="button" onClick={() => void finish()} disabled={pendingInput !== null || finishing} className="button-secondary">Finalizar conversación</button>}
      </form>
      {finishError && <div className="mt-2"><ErrorNotice message={finishError} /></div>}
    </div>
  );
}
