import {
  getAgentDetail,
  getRun,
  listActiveModels,
  listActiveTools,
  listAgentVersions,
  listKnowledgeBases,
  listKnowledgeDocuments,
  getKnowledgeBase,
  listModels,
  listTools,
} from "@/lib/api/client";
import { ModelSize } from "@/lib/api/types";
import type {
  AgentDetail,
  AgentVersion,
  CatalogModel,
  CatalogTool,
  KnowledgeBase,
  KnowledgeDocument,
  RunRecord,
} from "@/lib/api/types";
import { latestJustification } from "@/lib/specForm";

/** Everything the review page of an agent needs. */
export interface AgentReviewData {
  detail: AgentDetail;
  justification: string | null;
  models: CatalogModel[];
  tools: CatalogTool[];
  knowledgeBases: KnowledgeBase[];
}

/** Everything the detail page of an agent needs, apart from the metrics, which have their own filter. */
export interface AgentOverviewData {
  detail: AgentDetail;
  versions: AgentVersion[];
}

/** Everything the page of a knowledge base needs. */
export interface KnowledgeBaseData {
  base: KnowledgeBase;
  documents: KnowledgeDocument[];
}

/** Everything the trace page of a run needs. */
export interface RunTraceData {
  run: RunRecord;
  agentName: string;
  models: CatalogModel[];
  tools: CatalogTool[];
}

function canChat(model: CatalogModel): boolean {
  return model.size !== ModelSize.EMBEDDING;
}

/**
 * Loads an agent with the catalogs a person can choose from when adjusting it.
 *
 * Exists because the spec form needs all of it at once. Embedding models are left out because the
 * backend rejects them in a spec.
 *
 * @param agentId - The agent to review.
 * @returns The agent, the reasons of the designer and the options.
 */
export async function loadAgentReview(agentId: string): Promise<AgentReviewData> {
  const [detail, versions, models, tools, knowledgeBases] = await Promise.all([
    getAgentDetail(agentId),
    listAgentVersions(agentId),
    listActiveModels(),
    listActiveTools(),
    listKnowledgeBases(),
  ]);
  return {
    detail,
    justification: latestJustification(versions),
    models: models.filter(canChat),
    tools,
    knowledgeBases,
  };
}

/**
 * Loads an agent with the history of its versions.
 *
 * @param agentId - The agent to open.
 * @returns The agent and its versions, oldest first.
 */
export async function loadAgentOverview(agentId: string): Promise<AgentOverviewData> {
  const [detail, versions] = await Promise.all([getAgentDetail(agentId), listAgentVersions(agentId)]);
  return { detail, versions };
}

/**
 * Loads a knowledge base with what it holds.
 *
 * @param knowledgeBaseId - The base to open.
 * @returns The base and its current documents.
 */
export async function loadKnowledgeBase(knowledgeBaseId: string): Promise<KnowledgeBaseData> {
  const [base, documents] = await Promise.all([getKnowledgeBase(knowledgeBaseId), listKnowledgeDocuments(knowledgeBaseId)]);
  return { base, documents };
}

/**
 * Loads a run with what its identifiers refer to.
 *
 * Exists because the steps only hold the identifiers of models and tools, and a trace must name them.
 * It reads the whole catalogs, since a past step may have used a retired entry.
 *
 * @param runId - The run to open.
 * @returns The run, the name of its agent and the catalogs.
 */
export async function loadRunTrace(runId: string): Promise<RunTraceData> {
  const [run, models, tools] = await Promise.all([getRun(runId), listModels(), listTools()]);
  const { agent } = await getAgentDetail(run.agent_id);
  return { run, agentName: agent.name, models, tools };
}
