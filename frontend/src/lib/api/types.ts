/**
 * Mirrors of the backend's enums and `artifacts.py` contracts.
 *
 * Exists so the frontend compares against closed sets instead of retyping literals. Amounts travel as
 * decimal strings because the backend serializes `Decimal` that way, sometimes as `0E-8`.
 */

/** Mirrors `AgentStatus` of `bia/agents/artifacts.py`. */
export const AgentStatus = {
  DRAFT: "draft",
  TESTING: "testing",
  PUBLISHED: "published",
  ARCHIVED: "archived",
} as const;
export type AgentStatus = (typeof AgentStatus)[keyof typeof AgentStatus];

/** Mirrors `AgentKind` of `bia/agents/artifacts.py`. */
export const AgentKind = { USER: "user", SYSTEM: "system" } as const;
export type AgentKind = (typeof AgentKind)[keyof typeof AgentKind];

/** Mirrors `DuplicateVerdict` of `bia/builder/artifacts.py`. */
export const DuplicateVerdict = {
  EXISTS: "exists",
  SIMILAR: "similar",
  NOT_EXISTS: "not_exists",
} as const;
export type DuplicateVerdict = (typeof DuplicateVerdict)[keyof typeof DuplicateVerdict];

/** Mirrors `EvalVerdict` of `bia/evals/artifacts.py`. */
export const EvalVerdict = { PASS: "pass", FAIL: "fail" } as const;
export type EvalVerdict = (typeof EvalVerdict)[keyof typeof EvalVerdict];

/** Mirrors `EvalCaseOrigin` of `bia/evals/artifacts.py`. */
export const EvalCaseOrigin = { GENERATED: "generated", MANUAL: "manual" } as const;
export type EvalCaseOrigin = (typeof EvalCaseOrigin)[keyof typeof EvalCaseOrigin];

/** Mirrors `RunStatus` of `bia/tracing/artifacts.py`. */
export const RunStatus = { RUNNING: "running", SUCCEEDED: "succeeded", FAILED: "failed" } as const;
export type RunStatus = (typeof RunStatus)[keyof typeof RunStatus];

/** Mirrors `RunOrigin` of `bia/tracing/artifacts.py`. */
export const RunOrigin = {
  PLAYGROUND: "playground",
  EVAL: "eval",
  BUILDER: "builder",
  PRODUCTION: "production",
} as const;
export type RunOrigin = (typeof RunOrigin)[keyof typeof RunOrigin];

/** Mirrors `StepType` of `bia/tracing/artifacts.py`. */
export const StepType = {
  LLM_CALL: "llm_call",
  TOOL_CALL: "tool_call",
  RETRIEVAL: "retrieval",
} as const;
export type StepType = (typeof StepType)[keyof typeof StepType];

/** Mirrors `ModelSize` of `bia/catalog/models/artifacts.py`. */
export const ModelSize = { LARGE: "large", SMALL: "small", EMBEDDING: "embedding" } as const;
export type ModelSize = (typeof ModelSize)[keyof typeof ModelSize];

/** Mirrors `OrchestrationType` of `bia/orchestrations/artifacts.py`. */
export const OrchestrationType = { SINGLE_AGENT: "single_agent", SEQUENTIAL: "sequential" } as const;
export type OrchestrationType = (typeof OrchestrationType)[keyof typeof OrchestrationType];

/** Mirrors `DocumentType` of `bia/rag/artifacts.py`. */
export const DocumentType = { TARIFF: "tariff", PROCEDURE: "procedure", FAQ: "faq" } as const;
export type DocumentType = (typeof DocumentType)[keyof typeof DocumentType];

/** Mirrors the member of `ToolName` that needs a knowledge base, in `bia/catalog/tools/artifacts.py`. */
export const KNOWLEDGE_TOOL_NAME = "buscar_conocimiento";

/** Mirrors `AgentSpec`. */
export interface AgentSpec {
  purpose: string;
  system_prompt: string;
  model_id: string;
  tool_names: string[];
  knowledge_base_id: string | null;
  guardrails: string[];
  max_iterations: number;
}

/** Mirrors `AgentSpecPatch`: only the fields that change; a null knowledge base detaches it. */
export type AgentSpecPatch = Partial<AgentSpec>;

/** Mirrors `AgentIdentityPatch`: only the fields that change. */
export interface AgentIdentityPatch {
  name?: string;
  description?: string;
  owner_area?: string;
}

/** Mirrors `AgentMetrics`. */
export interface AgentMetrics {
  agent_id: string;
  total_runs: number;
  total_cost: string;
  latency_p50_ms: number | null;
  error_rate: number | null;
}

/** Mirrors `Agent`. */
export interface Agent {
  id: string;
  name: string;
  description: string;
  owner_area: string;
  creator: string;
  status: AgentStatus;
  kind: AgentKind;
  active_version_number: number | null;
  created_at: string;
  updated_at: string;
}

/** Mirrors `AgentVersion`. */
export interface AgentVersion {
  id: string;
  agent_id: string;
  version_number: number;
  spec: AgentSpec;
  designer_justification: string | null;
  created_at: string;
}

/** Mirrors `AgentDetail`. */
export interface AgentDetail {
  agent: Agent;
  active_version: AgentVersion | null;
}

/** Mirrors `AgentInventoryItem`. */
export interface AgentInventoryItem {
  id: string;
  name: string;
  owner_area: string;
  kind: AgentKind;
  status: AgentStatus;
  active_version_number: number | null;
  model_id: string | null;
  model_name: string | null;
  tool_names: string[];
  knowledge_base_id: string | null;
  knowledge_base_name: string | null;
  total_runs: number;
  total_cost: string;
}

/** Mirrors `ModelInventoryItem`. */
export interface ModelInventoryItem {
  id: string;
  name: string;
  provider: string;
  size: ModelSize;
  is_active: boolean;
  agents_using: number;
  input_tokens: number;
  output_tokens: number;
  total_cost: string;
}

/** Mirrors `OrchestrationStepInventoryItem`. */
export interface OrchestrationStep {
  orchestration_id: string;
  step_order: number;
  agent_id: string;
  agent_name: string;
  agent_status: AgentStatus;
  model_id: string | null;
  model_name: string | null;
  tool_names: string[];
  receives_context: string;
  delivers_output: string;
}

/** Mirrors `OrchestrationInventoryItem`. */
export interface OrchestrationInventoryItem {
  id: string;
  name: string;
  description: string;
  orchestration_type: OrchestrationType;
  is_system: boolean;
  steps: OrchestrationStep[];
}

/** Mirrors `CatalogModel`, with only what the frontend reads. */
export interface CatalogModel {
  id: string;
  name: string;
  size: ModelSize;
  recommended_use: string;
}

/** Mirrors `CatalogTool`, with only what the frontend reads. */
export interface CatalogTool {
  id: string;
  name: string;
  description: string;
}

/** Mirrors `DuplicateCandidate`. */
export interface DuplicateCandidate {
  agent_id: string;
  name: string;
  description: string;
  similarity: number;
}

/** Mirrors `DuplicateCheckResult`. */
export interface DuplicateCheckResult {
  verdict: DuplicateVerdict;
  candidate: DuplicateCandidate | null;
  reason: string;
}

/** Mirrors `AgentProposalRequest`. */
export interface AgentProposalRequest {
  description: string;
  owner_area: string;
  creator: string;
}

/** Mirrors `ProposedAgent`, with only what the frontend reads. */
export interface ProposedAgent {
  agent: AgentDetail;
}

/** Mirrors `KnowledgeBaseDraft`. */
export interface KnowledgeBaseDraft {
  name: string;
  description: string;
}

/** Mirrors `KnowledgeBase`. */
export interface KnowledgeBase extends KnowledgeBaseDraft {
  id: string;
  created_at: string;
}

/** Mirrors `DocumentDraft`. */
export interface DocumentDraft {
  title: string;
  document_type: DocumentType;
  content: string;
  valid_from: string | null;
  valid_until: string | null;
}

/** Mirrors `KnowledgeDocument`. */
export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  title: string;
  document_type: DocumentType;
  valid_from: string | null;
  valid_until: string | null;
  chunk_count: number;
  created_at: string;
}

/** Mirrors `IngestionResult`, with only what the frontend reads. */
export interface IngestionResult {
  document_id: string;
  chunks_ingested: number;
}

/** Mirrors `EvalCaseDraft`. */
export interface EvalCaseDraft {
  input: string;
  expected_behavior: string;
}

/** Mirrors `EvalCase`. */
export interface EvalCase {
  id: string;
  agent_id: string;
  input: string;
  expected_behavior: string;
  origin: EvalCaseOrigin;
  created_at: string;
}

/** Mirrors `EvalResult`. */
export interface EvalResult {
  id: string;
  output: string;
  verdict: EvalVerdict;
  score: number;
  judge_reason: string;
}

/** Mirrors `EvalCaseOutcome`. */
export interface EvalCaseOutcome {
  case: EvalCase;
  result: EvalResult | null;
}

/** Mirrors `EvalReport`. */
export interface EvalReport {
  agent_id: string;
  agent_version_id: string;
  version_number: number;
  threshold_percent: number;
  minimum_cases: number;
  total_cases: number;
  passed_cases: number;
  pass_percent: number;
  passes_gate: boolean;
  outcomes: EvalCaseOutcome[];
}

/** Mirrors `AgentRunResult`. */
export interface AgentRunResult {
  run_id: string;
  status: RunStatus;
  output: string | null;
  error: string | null;
}

/** Mirrors `RunStepRecord`. */
export interface RunStep {
  id: string;
  run_id: string;
  step_order: number;
  step_type: StepType;
  model_id: string | null;
  tool_id: string | null;
  input: unknown;
  output: unknown;
  input_tokens: number;
  output_tokens: number;
  cost: string;
  latency_ms: number;
  error: string | null;
  created_at: string;
}

/** Mirrors `RunRecord`. */
export interface RunRecord {
  id: string;
  agent_id: string;
  agent_version_id: string;
  origin: RunOrigin;
  input: string;
  output: string | null;
  status: RunStatus;
  error: string | null;
  total_tokens: number;
  total_cost: string;
  latency_ms: number | null;
  started_at: string;
  finished_at: string | null;
  steps: RunStep[];
}
