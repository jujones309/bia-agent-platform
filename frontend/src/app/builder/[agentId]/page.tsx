import { AgentReview } from "@/components/builder/AgentReview";

/**
 * Shows the review, evals and publication of an agent.
 *
 * @param props.params - The route, with the agent to review.
 * @returns The page.
 */
export default async function AgentReviewPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return <AgentReview agentId={agentId} />;
}
