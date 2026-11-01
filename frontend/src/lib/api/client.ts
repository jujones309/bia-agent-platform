import { readPassword, writePassword } from "@/lib/api/credentials";
import type {
  Agent,
  AgentDetail,
  AgentInventoryItem,
  AgentProposalRequest,
  AgentRunResult,
  AgentSpecPatch,
  AgentVersion,
  CatalogModel,
  CatalogTool,
  DuplicateCheckResult,
  EvalCase,
  EvalReport,
  ModelInventoryItem,
  OrchestrationInventoryItem,
  ProposedAgent,
  RunRecord,
} from "@/lib/api/types";

const HttpMethod = { GET: "GET", POST: "POST", PATCH: "PATCH" } as const;
type HttpMethod = (typeof HttpMethod)[keyof typeof HttpMethod];

const STATUS_UNAUTHORIZED = 401;
const STATUS_NETWORK_FAILURE = 0;
const RUNS_PAGE_SIZE = 50;

/**
 * Signals that the backend rejected a request or could not be reached.
 *
 * Exists so components show the backend's explanation instead of a generic failure; thrown by every
 * function of this module. A `status` of 0 means no response arrived.
 */
export class ApiError extends Error {
  /**
   * @param status - The HTTP status of the response, or 0 if there was none.
   * @param message - The explanation to show to the person.
   */
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildUrl(path: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!baseUrl) throw new ApiError(STATUS_NETWORK_FAILURE, "Falta configurar NEXT_PUBLIC_API_URL.");
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

function buildHeaders(password: string | null, hasBody: boolean): HeadersInit {
  return {
    Authorization: `Basic ${btoa(`bia:${password ?? ""}`)}`,
    ...(hasBody ? { "Content-Type": "application/json" } : {}),
  };
}

function describeValidationEntry(entry: { msg?: string }): string {
  return entry.msg ?? JSON.stringify(entry);
}

function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(describeValidationEntry).join("; ");
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : null;
}

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `El backend respondió ${response.status}.`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    return describeDetail(body.detail) ?? fallback;
  } catch {
    return fallback;
  }
}

async function send(
  method: HttpMethod,
  path: string,
  password: string | null,
  body?: unknown,
): Promise<Response> {
  try {
    return await fetch(buildUrl(path), {
      method,
      // Without this, a 401 could open the browser's own password dialog.
      credentials: "omit",
      headers: buildHeaders(password, body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(STATUS_NETWORK_FAILURE, "No se pudo conectar con el backend.");
  }
}

async function request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
  const response = await send(method, path, readPassword(), body);
  if (response.status === STATUS_UNAUTHORIZED) writePassword(null);
  if (!response.ok) throw new ApiError(response.status, await readErrorMessage(response));
  return (await response.json()) as T;
}

/**
 * Checks the shared password against the backend.
 *
 * Exists so the login form can tell a wrong password from a backend that is down.
 *
 * @param password - The password the person typed.
 * @returns True if the backend accepts it.
 * @throws ApiError if the backend fails or cannot be reached.
 */
export async function verifyPassword(password: string): Promise<boolean> {
  const response = await send(HttpMethod.GET, "/tools", password);
  if (response.status === STATUS_UNAUTHORIZED) return false;
  if (!response.ok) throw new ApiError(response.status, await readErrorMessage(response));
  return true;
}

/** Reads `GET /inventory/agents`. @returns Every agent with its configuration and cost. */
export function listAgentInventory(): Promise<AgentInventoryItem[]> {
  return request(HttpMethod.GET, "/inventory/agents");
}

/** Reads `GET /inventory/models`. @returns Every model with its adoption and consumption. */
export function listModelInventory(): Promise<ModelInventoryItem[]> {
  return request(HttpMethod.GET, "/inventory/models");
}

/** Reads `GET /inventory/orchestrations`. @returns Every flow with its steps in order. */
export function listOrchestrationInventory(): Promise<OrchestrationInventoryItem[]> {
  return request(HttpMethod.GET, "/inventory/orchestrations");
}

/** Reads `GET /agents`. @returns Every agent of the registry. */
export function listAgents(): Promise<Agent[]> {
  return request(HttpMethod.GET, "/agents");
}

/** Reads `GET /models`, every entry, so old traces can still name retired models. @returns The catalog. */
export function listModels(): Promise<CatalogModel[]> {
  return request(HttpMethod.GET, "/models");
}

/** Reads `GET /models?only_active=true`. @returns The models that a new version may choose. */
export function listActiveModels(): Promise<CatalogModel[]> {
  return request(HttpMethod.GET, "/models?only_active=true");
}

/** Reads `GET /tools`, every entry, so old traces can still name retired tools. @returns The catalog. */
export function listTools(): Promise<CatalogTool[]> {
  return request(HttpMethod.GET, "/tools");
}

/** Reads `GET /tools?only_active=true`. @returns The tools that a new version may choose. */
export function listActiveTools(): Promise<CatalogTool[]> {
  return request(HttpMethod.GET, "/tools?only_active=true");
}

/**
 * Calls `POST /builder/check`.
 *
 * @param description - The need, in natural language.
 * @returns The verdict, with the agent that resembles it if there is one.
 */
export function checkDuplicates(description: string): Promise<DuplicateCheckResult> {
  return request(HttpMethod.POST, "/builder/check", { description });
}

/**
 * Calls `POST /builder/propose`, which creates the agent in draft.
 *
 * @param proposal - The need and who will own the agent.
 * @returns The new draft agent.
 */
export function proposeAgent(proposal: AgentProposalRequest): Promise<ProposedAgent> {
  return request(HttpMethod.POST, "/builder/propose", proposal);
}

/**
 * Reads `GET /agents/{id}`.
 *
 * @param agentId - The agent to read.
 * @returns The agent and its active version.
 */
export function getAgentDetail(agentId: string): Promise<AgentDetail> {
  return request(HttpMethod.GET, `/agents/${agentId}`);
}

/**
 * Reads `GET /agents/{id}/versions`.
 *
 * @param agentId - The agent to read.
 * @returns Its versions, oldest first.
 */
export function listAgentVersions(agentId: string): Promise<AgentVersion[]> {
  return request(HttpMethod.GET, `/agents/${agentId}/versions`);
}

/**
 * Calls `PATCH /agents/{id}`, which creates a version that becomes the active one.
 *
 * @param agentId - The agent to change.
 * @param patch - The fields of the spec that change.
 * @returns The agent with its new version.
 */
export function patchAgent(agentId: string, patch: AgentSpecPatch): Promise<AgentDetail> {
  return request(HttpMethod.PATCH, `/agents/${agentId}`, patch);
}

/**
 * Reads `GET /agents/{id}/evals`, which spends nothing.
 *
 * @param agentId - The agent to measure.
 * @returns The standing of its active version, case by case.
 */
export function getEvalReport(agentId: string): Promise<EvalReport> {
  return request(HttpMethod.GET, `/agents/${agentId}/evals`);
}

/**
 * Calls `POST /agents/{id}/eval-cases/generate`.
 *
 * @param agentId - The agent to write cases for.
 * @returns The stored cases.
 */
export function generateEvalCases(agentId: string): Promise<EvalCase[]> {
  return request(HttpMethod.POST, `/agents/${agentId}/eval-cases/generate`);
}

/**
 * Calls `POST /agents/{id}/evals/run`, which can take minutes.
 *
 * @param agentId - The agent to evaluate.
 * @returns The standing of its active version, case by case.
 */
export function runEvals(agentId: string): Promise<EvalReport> {
  return request(HttpMethod.POST, `/agents/${agentId}/evals/run`);
}

/**
 * Calls `POST /agents/{id}/publish`.
 *
 * @param agentId - The agent to publish.
 * @returns The published agent.
 * @throws ApiError with status 409 if the agent does not pass the gate.
 */
export function publishAgent(agentId: string): Promise<AgentDetail> {
  return request(HttpMethod.POST, `/agents/${agentId}/publish`);
}

/**
 * Calls `POST /agents/{id}/run`.
 *
 * @param agentId - The agent to execute.
 * @param input - The message of the person.
 * @returns The answer, or the reason there is none, with the run that traces it.
 */
export function runAgent(agentId: string, input: string): Promise<AgentRunResult> {
  return request(HttpMethod.POST, `/agents/${agentId}/run`, { input });
}

/**
 * Reads `GET /runs`.
 *
 * @param agentId - The only agent to include, or null for all of them.
 * @returns The most recent runs with their steps, newest first.
 */
export function listRuns(agentId: string | null): Promise<RunRecord[]> {
  const filter = agentId ? `&agent_id=${agentId}` : "";
  return request(HttpMethod.GET, `/runs?limit=${RUNS_PAGE_SIZE}${filter}`);
}

/**
 * Reads `GET /runs/{id}`.
 *
 * @param runId - The run to read.
 * @returns The run with its steps in order.
 */
export function getRun(runId: string): Promise<RunRecord> {
  return request(HttpMethod.GET, `/runs/${runId}`);
}
