"use client";

import Link from "next/link";
import { useCallback } from "react";
import { AgentIdentityForm } from "@/components/agents/AgentIdentityForm";
import { AgentMetricsCard } from "@/components/agents/AgentMetricsCard";
import { AgentVersionList } from "@/components/agents/AgentVersionList";
import { AgentStatusBadge } from "@/components/ui/Badge";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { archiveAgent } from "@/lib/api/client";
import { AgentKind, AgentStatus } from "@/lib/api/types";
import type { Agent } from "@/lib/api/types";
import { loadAgentOverview } from "@/lib/loaders";
import { agentReviewPath, playgroundPath } from "@/lib/routes";

const ARCHIVE_CONFIRMATION = "¿Archivar este agente? Sale de la búsqueda de duplicados y ya no se puede editar ni publicar. Sus trazas se conservan. Desde la interfaz no se puede deshacer.";

function AgentActions({ agent, onArchived }: { agent: Agent; onArchived: () => void }) {
  const { isRunning, error, run } = useAsyncAction();

  async function archive(): Promise<void> {
    await archiveAgent(agent.id);
    onArchived();
  }

  function handleArchive(): void {
    if (window.confirm(ARCHIVE_CONFIRMATION)) void run(archive);
  }

  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link href={playgroundPath(agent.id)} className="button-secondary">Probar</Link>
        <Link href={agentReviewPath(agent.id)} className="button-secondary">Ajustar spec y evals</Link>
        <button type="button" onClick={() => handleArchive()} disabled={isRunning} className="button-secondary">{isRunning ? "Archivando…" : "Archivar"}</button>
      </div>
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

/**
 * Gathers what can be read and done on one agent: identity, metrics, versions and archiving.
 *
 * Exists so the people who own an agent manage it without the API. System agents and archived ones
 * are read-only: the code owns the former, and the latter are retired.
 *
 * @param props.agentId - The agent to open.
 * @returns The page content.
 */
export function AgentOverview({ agentId }: { agentId: string }) {
  const loader = useCallback(() => loadAgentOverview(agentId), [agentId]);
  const { data, error, reload } = useApiResource(loader);

  if (!data) return <ResourcePlaceholder error={error} />;
  const { agent, active_version: version } = data.detail;
  const isManageable = agent.kind === AgentKind.USER && agent.status !== AgentStatus.ARCHIVED;
  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="page-title">{agent.name}</h1>
        <p className="mt-1 text-sm text-slate-600">{agent.owner_area} · Creado por {agent.creator} · <AgentStatusBadge status={agent.status} /></p>
      </div>
      {isManageable && <AgentActions agent={agent} onArchived={() => reload()} />}
      {isManageable ? <AgentIdentityForm key={agent.updated_at} agent={agent} onSaved={() => reload()} /> : <p className="card text-sm text-slate-600">{agent.description}</p>}
      <AgentMetricsCard agentId={agent.id} />
      <AgentVersionList agent={agent} versions={data.versions} activeVersionNumber={version?.version_number ?? null} canActivate={isManageable} onActivated={() => reload()} />
    </div>
  );
}
