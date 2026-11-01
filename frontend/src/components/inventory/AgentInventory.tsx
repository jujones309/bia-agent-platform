"use client";

import Link from "next/link";
import { AgentStatusBadge } from "@/components/ui/Badge";
import { DataTable } from "@/components/ui/DataTable";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { listAgentInventory } from "@/lib/api/client";
import { AgentKind, AgentStatus } from "@/lib/api/types";
import type { AgentInventoryItem } from "@/lib/api/types";
import { formatCost, formatCount, orDash } from "@/lib/format";
import { agentReviewPath, playgroundPath } from "@/lib/routes";

const HEADERS = ["Agente", "Área", "Estado", "Modelo", "Runs", "Costo", ""];

function canContinueBuilding(agent: AgentInventoryItem): boolean {
  const isUnpublished = agent.status === AgentStatus.DRAFT || agent.status === AgentStatus.TESTING;
  return agent.kind === AgentKind.USER && isUnpublished;
}

function AgentRow({ agent }: { agent: AgentInventoryItem }) {
  return (
    <tr>
      <td className="font-medium">
        {agent.name}
        {agent.kind === AgentKind.SYSTEM && <span className="ml-2 text-xs font-normal text-slate-500">Sistema</span>}
      </td>
      <td>{agent.owner_area}</td>
      <td><AgentStatusBadge status={agent.status} /></td>
      <td className="whitespace-nowrap">{orDash(agent.model_name)}</td>
      <td>{formatCount(agent.total_runs)}</td>
      <td className="whitespace-nowrap">{formatCost(agent.total_cost)}</td>
      <td className="space-x-3 whitespace-nowrap">
        {agent.kind === AgentKind.USER && <Link href={playgroundPath(agent.id)} className="text-link">Probar</Link>}
        {canContinueBuilding(agent) && <Link href={agentReviewPath(agent.id)} className="text-link">Continuar</Link>}
      </td>
    </tr>
  );
}

function renderAgentRow(agent: AgentInventoryItem) {
  return <AgentRow key={agent.id} agent={agent} />;
}

/**
 * Shows every agent with its state, model, runs and cost.
 *
 * Exists as the overview of what exists in Bia. Agents still being built offer a way back to the
 * Builder, because a draft cannot be deleted and otherwise could not be reached again.
 *
 * @returns The page content.
 */
export function AgentInventory() {
  const { data, error } = useApiResource(listAgentInventory);
  return (
    <>
      <h1 className="page-title">Agentes</h1>
      <p className="page-intro">Todos los agentes de Bia. Los runs y el costo incluyen evals y playground.</p>
      {data ? <DataTable headers={HEADERS}>{data.map(renderAgentRow)}</DataTable> : <ResourcePlaceholder error={error} />}
    </>
  );
}
