"use client";

import { useCallback, useState } from "react";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { getAgentMetrics } from "@/lib/api/client";
import { RunOrigin } from "@/lib/api/types";
import type { AgentMetrics } from "@/lib/api/types";
import { formatCost, formatCount, formatLatency, formatPercent, orDash } from "@/lib/format";
import { RUN_ORIGIN_LABEL } from "@/lib/labels";

const PERCENT_SCALE = 100;

function renderOriginOption(origin: RunOrigin) {
  return <option key={origin} value={origin}>{RUN_ORIGIN_LABEL[origin]}</option>;
}

function formatErrorRate(rate: number | null): string {
  return orDash(rate === null ? null : formatPercent(rate * PERCENT_SCALE));
}

function formatMedianLatency(milliseconds: number | null): string {
  return formatLatency(milliseconds === null ? null : Math.round(milliseconds));
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  );
}

function MetricValues({ metrics }: { metrics: AgentMetrics }) {
  return (
    <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <Metric label="Runs" value={formatCount(metrics.total_runs)} />
      <Metric label="Costo total" value={formatCost(metrics.total_cost)} />
      <Metric label="Latencia mediana" value={formatMedianLatency(metrics.latency_p50_ms)} />
      <Metric label="Tasa de error" value={formatErrorRate(metrics.error_rate)} />
    </dl>
  );
}

/**
 * Shows the runs, cost, speed and reliability of an agent, of every origin or of one.
 *
 * Exists because the totals mix evals and playground with real use, so a person must be able to separate
 * them to read how an agent behaves.
 *
 * @param props.agentId - The agent to summarize.
 * @returns The card.
 */
export function AgentMetricsCard({ agentId }: { agentId: string }) {
  const [origin, setOrigin] = useState<RunOrigin | "">("");
  const loader = useCallback(() => getAgentMetrics(agentId, origin || null), [agentId, origin]);
  const { data, error } = useApiResource(loader);

  return (
    <section className="card space-y-3">
      <h2 className="font-semibold">Métricas</h2>
      <label className="field-label max-w-xs">Origen
        <select value={origin} onChange={(event) => setOrigin(event.target.value as RunOrigin | "")} className="field-input">
          <option value="">Todos</option>
          {Object.values(RunOrigin).map(renderOriginOption)}
        </select>
      </label>
      {data ? <MetricValues metrics={data} /> : <ResourcePlaceholder error={error} />}
    </section>
  );
}
