import { AgentOverview } from "@/components/agents/AgentOverview";

/**
 * Shows the detail of an agent: identity, metrics, versions and archiving.
 *
 * @param props.params - The route, with the agent to open.
 * @returns The page.
 */
export default async function AgentDetailPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return <AgentOverview agentId={agentId} />;
}
