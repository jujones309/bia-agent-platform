import { Playground } from "@/components/playground/Playground";

/**
 * Shows the chat against an agent.
 *
 * @param props.params - The route, with the agent to talk to.
 * @returns The page.
 */
export default async function PlaygroundPage({ params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  return <Playground agentId={agentId} />;
}
