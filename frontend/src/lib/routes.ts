/**
 * The fixed pages of the application.
 *
 * Exists so links and the sidebar share one definition instead of retyping paths.
 */
export const Route = {
  AGENTS: "/agents",
  MODELS: "/models",
  ORCHESTRATIONS: "/orchestrations",
  BUILDER: "/builder",
  RUNS: "/runs",
} as const;
export type Route = (typeof Route)[keyof typeof Route];

/**
 * Builds the path of an agent's playground.
 *
 * @param agentId - The agent to talk to.
 * @returns The path of the page.
 */
export function playgroundPath(agentId: string): string {
  return `${Route.AGENTS}/${agentId}/playground`;
}

/**
 * Builds the path where an agent is reviewed, evaluated and published.
 *
 * @param agentId - The agent to review.
 * @returns The path of the page.
 */
export function agentReviewPath(agentId: string): string {
  return `${Route.BUILDER}/${agentId}`;
}

/**
 * Builds the path of a run's trace.
 *
 * @param runId - The run to open.
 * @returns The path of the page.
 */
export function runPath(runId: string): string {
  return `${Route.RUNS}/${runId}`;
}
