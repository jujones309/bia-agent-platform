import { RunTrace } from "@/components/runs/RunTrace";

/**
 * Shows the trace of a run.
 *
 * @param props.params - The route, with the run to open.
 * @returns The page.
 */
export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <RunTrace runId={runId} />;
}
