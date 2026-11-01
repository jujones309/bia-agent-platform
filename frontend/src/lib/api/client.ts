import { readPassword, writePassword } from "@/lib/api/credentials";
import type {
  Agent,
  AgentDetail,
  AgentIdentityPatch,
  AgentInventoryItem,
  AgentMetrics,
  AgentProposalRequest,
  AgentRunResult,
  AgentSpecPatch,
  AgentVersion,
  CatalogModel,
  CatalogTool,
  DocumentDraft,
  DuplicateCheckResult,
  EvalCase,
  EvalCaseDraft,
  EvalReport,
  IngestionResult,
  KnowledgeBase,
  KnowledgeBaseDraft,
  KnowledgeDocument,
  ModelInventoryItem,
  OrchestrationInventoryItem,
  ProposedAgent,
  RunOrigin,
  RunRecord,
} from "@/lib/api/types";

const HttpMethod = { GET: "GET", POST: "POST", PATCH: "PATCH", DELETE: "DELETE" } as const;
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

async function sendChecked(method: HttpMethod, path: string, body?: unknown): Promise<Response> {
  const response = await send(method, path, readPassword(), body);
  if (response.status === STATUS_UNAUTHORIZED) writePassword(null);
  if (!response.ok) throw new ApiError(response.status, await readErrorMessage(response));
  return response;
}

async function request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
  const response = await sendChecked(method, path, body);
  return (await response.json()) as T;
}

async function requestRemoval(path: string): Promise<void> {
  await sendChecked(HttpMethod.DELETE, path);
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
 * Calls `PATCH /agents/{id}/identity`, which embeds a new description.
 *
 * @param agentId - The agent to change.
 * @param patch - The fields of its identity that change.
 * @returns The agent with its new identity.
 */
export function updateAgentIdentity(agentId: string, patch: AgentIdentityPatch): Promise<AgentDetail> {
  return request(HttpMethod.PATCH, `/agents/${agentId}/identity`, patch);
}

/**
 * Calls `POST /agents/{id}/archive`.
 *
 * @param agentId - The agent to archive.
 * @returns The archived agent.
 */
export function archiveAgent(agentId: string): Promise<AgentDetail> {
  return request(HttpMethod.POST, `/agents/${agentId}/archive`);
}

/**
 * Calls `POST /agents/{id}/versions/{n}/activate`.
 *
 * @param agentId - The agent to change.
 * @param versionNumber - The version to go back to.
 * @returns The agent pointing at that version.
 */
export function activateAgentVersion(agentId: string, versionNumber: number): Promise<AgentDetail> {
  return request(HttpMethod.POST, `/agents/${agentId}/versions/${versionNumber}/activate`);
}

/**
 * Reads `GET /agents/{id}/metrics`.
 *
 * @param agentId - The agent to summarize.
 * @param origin - The only origin to count, or null for all of them.
 * @returns The aggregates of its runs.
 */
export function getAgentMetrics(agentId: string, origin: RunOrigin | null): Promise<AgentMetrics> {
  const filter = origin ? `?origin=${origin}` : "";
  return request(HttpMethod.GET, `/agents/${agentId}/metrics${filter}`);
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
 * Calls `POST /agents/{id}/eval-cases`.
 *
 * @param agentId - The agent the case evaluates.
 * @param draft - What to ask and what to expect.
 * @returns The stored case.
 */
export function addEvalCase(agentId: string, draft: EvalCaseDraft): Promise<EvalCase> {
  return request(HttpMethod.POST, `/agents/${agentId}/eval-cases`, draft);
}

/**
 * Calls `DELETE /agents/{id}/eval-cases/{case_id}`, which keeps the past results as history.
 *
 * @param agentId - The agent the case belongs to.
 * @param caseId - The case to retire.
 * @returns Nothing once it is retired.
 */
export function retireEvalCase(agentId: string, caseId: string): Promise<void> {
  return requestRemoval(`/agents/${agentId}/eval-cases/${caseId}`);
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
 * @param runId - The open conversation to continue; without it, a new one starts.
 * @returns The answer, or the reason there is none, with the run that traces it.
 */
export function runAgent(agentId: string, input: string, runId: string | null = null): Promise<AgentRunResult> {
  return request(HttpMethod.POST, `/agents/${agentId}/run`, runId ? { input, run_id: runId } : { input });
}

/**
 * Calls `POST /runs/{id}/finish`.
 *
 * @param runId - The open conversation to finish.
 * @returns The closed run.
 * @throws ApiError with status 409 if the run is not an open conversation.
 */
export function finishRun(runId: string): Promise<RunRecord> {
  return request(HttpMethod.POST, `/runs/${runId}/finish`);
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

/** Reads `GET /knowledge-bases`. @returns Every knowledge base, ordered by name. */
export function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return request(HttpMethod.GET, "/knowledge-bases");
}

/**
 * Reads `GET /knowledge-bases/{id}`.
 *
 * @param knowledgeBaseId - The base to read.
 * @returns The base.
 */
export function getKnowledgeBase(knowledgeBaseId: string): Promise<KnowledgeBase> {
  return request(HttpMethod.GET, `/knowledge-bases/${knowledgeBaseId}`);
}

/**
 * Calls `POST /knowledge-bases`.
 *
 * @param draft - The name and description of the base.
 * @returns The new base.
 */
export function createKnowledgeBase(draft: KnowledgeBaseDraft): Promise<KnowledgeBase> {
  return request(HttpMethod.POST, "/knowledge-bases", draft);
}

/**
 * Reads `GET /knowledge-bases/{id}/documents`.
 *
 * @param knowledgeBaseId - The base to read.
 * @returns Its current documents, ordered by title.
 */
export function listKnowledgeDocuments(knowledgeBaseId: string): Promise<KnowledgeDocument[]> {
  return request(HttpMethod.GET, `/knowledge-bases/${knowledgeBaseId}/documents`);
}

/**
 * Calls `POST /knowledge-bases/{id}/ingest`, which replaces a document with the same title.
 *
 * @param knowledgeBaseId - The base that receives the document.
 * @param draft - The document with its text.
 * @returns How many fragments were stored.
 */
export function ingestDocument(knowledgeBaseId: string, draft: DocumentDraft): Promise<IngestionResult> {
  return request(HttpMethod.POST, `/knowledge-bases/${knowledgeBaseId}/ingest`, draft);
}

/**
 * Calls `DELETE /knowledge-bases/{id}/documents/{document_id}`.
 *
 * @param knowledgeBaseId - The base the document belongs to.
 * @param documentId - The document to retire.
 * @returns Nothing once it is retired.
 */
export function retireDocument(knowledgeBaseId: string, documentId: string): Promise<void> {
  return requestRemoval(`/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`);
}

/**
 * Calls `DELETE /orchestrations/{id}`, which keeps the flow as history.
 *
 * @param orchestrationId - The flow to retire.
 * @returns Nothing once it is retired.
 */
export function retireOrchestration(orchestrationId: string): Promise<void> {
  return requestRemoval(`/orchestrations/${orchestrationId}`);
}
