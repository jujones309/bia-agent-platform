"use client";

import { useCallback, useState } from "react";
import { EvalStep } from "@/components/builder/EvalStep";
import { SpecForm } from "@/components/builder/SpecForm";
import { AgentStatusBadge } from "@/components/ui/Badge";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { AgentKind } from "@/lib/api/types";
import { loadAgentReview } from "@/lib/loaders";

const ReviewStage = { ADJUST: "adjust", EVALUATE: "evaluate" } as const;
type ReviewStage = (typeof ReviewStage)[keyof typeof ReviewStage];

/**
 * Takes an agent from its proposed spec to being published: adjust it, evaluate it and publish it.
 *
 * Exists as its own page, keyed by the agent, so a reload or a later visit can continue the work.
 *
 * @param props.agentId - The agent to review.
 * @returns The page content.
 */
export function AgentReview({ agentId }: { agentId: string }) {
  const [stage, setStage] = useState<ReviewStage>(ReviewStage.ADJUST);
  const loader = useCallback(() => loadAgentReview(agentId), [agentId]);
  const { data, error, reload } = useApiResource(loader);

  function handleSaved(): void {
    reload();
    setStage(ReviewStage.EVALUATE);
  }

  if (!data) return <ResourcePlaceholder error={error} />;
  const { agent, active_version: version } = data.detail;
  if (agent.kind === AgentKind.SYSTEM) return <ErrorNotice message="Los agentes de sistema no pasan por el Builder." />;
  if (!version) return <ErrorNotice message="Este agente no tiene una versión activa." />;
  return (
    <>
      <h1 className="page-title">{agent.name}</h1>
      <p className="page-intro">Versión {version.version_number} · <AgentStatusBadge status={agent.status} /></p>
      {stage === ReviewStage.ADJUST && <SpecForm key={version.id} agent={agent} version={version} review={data} onSaved={() => handleSaved()} />}
      {stage === ReviewStage.EVALUATE && <EvalStep key={version.id} agent={agent} onBack={() => setStage(ReviewStage.ADJUST)} onAgentChanged={() => reload()} />}
    </>
  );
}
