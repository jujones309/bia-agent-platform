"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { RunStatusBadge } from "@/components/ui/Badge";
import { DataTable } from "@/components/ui/DataTable";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { listAgents, listRuns } from "@/lib/api/client";
import type { Agent, RunRecord } from "@/lib/api/types";
import { findName, formatCost, formatCount, formatDateTime, formatLatency } from "@/lib/format";
import { RUN_ORIGIN_LABEL } from "@/lib/labels";
import { runPath } from "@/lib/routes";

const HEADERS = ["Inicio", "Agente", "Origen", "Estado", "Entrada", "Tokens", "Costo", "Latencia"];

function renderAgentOption(agent: Agent) {
  return <option key={agent.id} value={agent.id}>{agent.name}</option>;
}

function RunRow({ run, agentName }: { run: RunRecord; agentName: string }) {
  return (
    <tr>
      <td className="whitespace-nowrap"><Link href={runPath(run.id)} className="text-link">{formatDateTime(run.started_at)}</Link></td>
      <td className="whitespace-nowrap">{agentName}</td>
      <td>{RUN_ORIGIN_LABEL[run.origin]}</td>
      <td><RunStatusBadge status={run.status} /></td>
      <td className="max-w-xs truncate">{run.input}</td>
      <td>{formatCount(run.total_tokens)}</td>
      <td className="whitespace-nowrap">{formatCost(run.total_cost)}</td>
      <td className="whitespace-nowrap">{formatLatency(run.latency_ms)}</td>
    </tr>
  );
}

/**
 * Shows the most recent runs, of every agent or of one, with links to their traces.
 *
 * Exists so people can audit what agents did.
 *
 * @returns The page content.
 */
export function RunsExplorer() {
  const [agentId, setAgentId] = useState("");
  const runsLoader = useCallback(() => listRuns(agentId || null), [agentId]);
  const runs = useApiResource(runsLoader);
  const agents = useApiResource(listAgents);

  function renderRun(run: RunRecord) {
    return <RunRow key={run.id} run={run} agentName={findName(agents.data ?? [], run.agent_id) ?? run.agent_id} />;
  }

  return (
    <>
      <h1 className="page-title">Runs</h1>
      <p className="page-intro">Las 50 ejecuciones más recientes. Abre una para ver sus pasos.</p>
      <label className="field-label mb-4 max-w-sm">Agente
        <select value={agentId} onChange={(event) => setAgentId(event.target.value)} className="field-input">
          <option value="">Todos</option>
          {agents.data?.map(renderAgentOption)}
        </select>
      </label>
      {runs.data ? <DataTable headers={HEADERS}>{runs.data.map(renderRun)}</DataTable> : <ResourcePlaceholder error={runs.error} />}
    </>
  );
}
