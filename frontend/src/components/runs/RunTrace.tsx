"use client";

import { useCallback } from "react";
import { RunSteps } from "@/components/runs/RunSteps";
import { RunStatusBadge } from "@/components/ui/Badge";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { MarkdownText } from "@/components/ui/MarkdownText";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { formatCost, formatCount, formatDateTime, formatLatency } from "@/lib/format";
import { RUN_ORIGIN_LABEL } from "@/lib/labels";
import { loadRunTrace } from "@/lib/loaders";

/**
 * Shows what a run did, step by step, with its totals.
 *
 * Exists as the audit record of an answer: what it asked, what it used and what it cost.
 *
 * @param props.runId - The run to open.
 * @returns The page content.
 */
export function RunTrace({ runId }: { runId: string }) {
  const loader = useCallback(() => loadRunTrace(runId), [runId]);
  const { data, error } = useApiResource(loader);
  if (!data) return <ResourcePlaceholder error={error} />;
  const { run, agentName, models, tools } = data;
  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="page-title">Traza de {agentName}</h1>
        <p className="mt-1 text-sm text-slate-600">
          <RunStatusBadge status={run.status} /> · {RUN_ORIGIN_LABEL[run.origin]} · {formatDateTime(run.started_at)} · {formatCount(run.total_tokens)} tokens · {formatCost(run.total_cost)} · {formatLatency(run.latency_ms)}
        </p>
      </div>
      <section className="card space-y-2 text-sm">
        <p className="whitespace-pre-wrap"><span className="font-medium">Entrada: </span>{run.input}</p>
        {run.output && <div><p className="font-medium">Salida:</p><MarkdownText text={run.output} /></div>}
        {run.error && <ErrorNotice message={run.error} />}
      </section>
      <RunSteps steps={run.steps} models={models} tools={tools} />
    </div>
  );
}
